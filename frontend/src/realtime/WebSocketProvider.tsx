/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import { queryClient } from "@/hooks/queryClient";
import { Broker } from "./subscriptions";

type Handler = (msg: unknown) => void;
type Subscribe = (channel: string, handler: Handler) => () => void;
type Ctx = { subscribe: Subscribe };

const WebSocketContext = createContext<Ctx | null>(null);

function pathForChannel(channel: string): string {
  if (channel.startsWith("thread.")) {
    return `/ws/threads/${channel.slice("thread.".length)}/`;
  }
  if (channel.startsWith("snapshot.")) {
    return `/ws/snapshots/${channel.slice("snapshot.".length)}/`;
  }
  if (channel === "notifications" || channel.startsWith("notifications.")) {
    return `/ws/notifications/`;
  }
  throw new Error(`Unknown channel: ${channel}`);
}

const WS_CONNECTING = 0;

// A replay_gap frame means the server's replay buffer could not cover our
// `?since=` — events were irrecoverably lost, so the affected channel's server
// state must be refetched instead of trusting the stream.
function invalidateChannelQueries(channel: string): void {
  if (channel.startsWith("thread.")) {
    const id = Number(channel.slice("thread.".length));
    void queryClient.invalidateQueries({ queryKey: ["thread", id] });
  }
}

// Closing a socket mid-handshake makes the browser log a noisy (but harmless)
// "WebSocket is closed before the connection is established" warning. Defer the
// close until the socket finishes connecting so teardown is clean. Callers remove
// the socket from the active map first, so its close handler won't reconnect.
function closeSocket(ws: WebSocket): void {
  if (ws.readyState === WS_CONNECTING) {
    ws.addEventListener("open", () => ws.close(), { once: true });
  } else {
    ws.close();
  }
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

// Mirrors the backend replay buffer (event_log._MAX_EVENTS): a genuine
// replay/live duplicate is always an event still inside the buffered tail, so
// its seq trails the cursor by less than the buffer size.
const REPLAY_BUFFER_EVENTS = 256;
// Mirrors the backend seq-counter TTL (event_log._TTL_SECONDS = 1h): the
// counter restarts only after >=1h with no recorded events, so a backwards seq
// arriving that long after the cursor last advanced is a restart, not a
// duplicate. Kept below the backend TTL so receipt-latency skew can't
// misclassify (real duplicates arrive within moments of the original anyway).
const SEQ_RESTART_IDLE_MS = 55 * 60 * 1000;

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const broker = useMemo(() => new Broker(), []);
  const sockets = useRef(new Map<string, WebSocket>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const attempts = useRef(new Map<string, number>());
  // Per-channel last-received server `seq` (thread.<id> events carry one) plus
  // the wall-clock time it advanced. On a reconnect we send the seq as `?since=`
  // so the server replays events emitted during the gap; without it, a drop
  // silently loses those events. The timestamp detects a server-side counter
  // restart (see the message handler).
  const lastSeq = useRef(new Map<string, { seq: number; at: number }>());
  // Set once the provider unmounts so in-flight close handlers / timers don't reopen.
  const disposed = useRef(false);
  // Empty VITE_WS_BASE_URL means same-origin: build the base from the current
  // location so the WebSocket goes through the Vite dev proxy (/ws → web:8000).
  const configured = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const wsBase = configured && configured.length > 0 ? configured : `${proto}://${window.location.host}`;

  const ctx = useMemo<Ctx>(() => {
    function openForChannel(channel: string): void {
      if (sockets.current.has(channel)) return;
      // First connect: no `?since=`. Reconnect: we have a last-seen seq, so ask the
      // server to replay everything after it (ThreadConsumer keeps a capped tail).
      // The presence of a seq is itself the first-connect-vs-reconnect signal.
      const since = lastSeq.current.get(channel)?.seq;
      const path = pathForChannel(channel);
      const url = since !== undefined ? `${wsBase}${path}?since=${since}` : `${wsBase}${path}`;
      const ws = new WebSocket(url);
      ws.addEventListener("message", (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if ((msg as { type?: unknown })?.type === "replay_gap") {
            // Handled BEFORE the seq filter: a gap frame must never be dropped,
            // and it also means the server's seq counter may have restarted
            // below our cursor (Redis flush, 1h idle expiry of the counter
            // key). Reset the cursor so post-gap events with restarted seqs
            // are dispatched — otherwise every subsequent event is silently
            // dropped as a "duplicate" and the streaming UI goes dead — and so
            // the next reconnect is a fresh first-connect, not a stale ?since=.
            lastSeq.current.delete(channel);
            invalidateChannelQueries(channel);
            broker.dispatch(channel, msg);
            return;
          }
          const seq = (msg as { seq?: unknown })?.seq;
          if (typeof seq === "number") {
            // Seq-carrying events are exactly-once: on reconnect the server's
            // replay tail overlaps the live feed (record-then-broadcast,
            // group_add-then-replay), so a duplicate (seq <= cursor) must be
            // dropped, never re-dispatched — text_delta handlers append
            // non-idempotently. Seq-less channels dispatch unconditionally.
            const cursor = lastSeq.current.get(channel);
            if (cursor !== undefined && seq <= cursor.seq) {
              // BUT: a backwards seq on a live connection can also be the
              // server's counter restarting under us (Redis flush, 1h idle
              // expiry of the counter key) with no reconnect — so no
              // replay_gap frame ever arrives to reset the cursor. A real
              // duplicate is a just-delivered event still inside the replay
              // buffer; a restart lands far below the cursor or after the
              // counter's idle TTL. Treat that as a fresh stream and dispatch,
              // or every subsequent event is silently dropped as a
              // "duplicate" and the streaming UI goes dead.
              const restarted =
                cursor.seq - seq >= REPLAY_BUFFER_EVENTS ||
                Date.now() - cursor.at >= SEQ_RESTART_IDLE_MS;
              if (!restarted) return;
            }
            lastSeq.current.set(channel, { seq, at: Date.now() });
          }
          broker.dispatch(channel, msg);
        } catch {
          // ignore malformed payloads
        }
      });
      // A healthy connection resets the backoff so the next drop retries fast.
      ws.addEventListener("open", () => {
        attempts.current.set(channel, 0);
      });
      // An unexpected close (server restart, network blip, idle timeout) must
      // reopen the socket — otherwise the UI silently stops receiving events
      // (e.g. a stream's message_done never arrives, leaving a stuck Stop button).
      ws.addEventListener("close", () => {
        // If this socket is no longer the active one for the channel, the close
        // was an intentional teardown (closeIfUnused deletes from the map first)
        // or a stale socket — don't resurrect it.
        if (sockets.current.get(channel) !== ws) return;
        sockets.current.delete(channel);
        if (disposed.current || !broker.channels().includes(channel)) return;
        const n = (attempts.current.get(channel) ?? 0) + 1;
        attempts.current.set(channel, n);
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** (n - 1), RECONNECT_MAX_MS);
        const timer = setTimeout(() => {
          timers.current.delete(channel);
          if (disposed.current || !broker.channels().includes(channel)) return;
          openForChannel(channel);
        }, delay);
        timers.current.set(channel, timer);
      });
      sockets.current.set(channel, ws);
    }

    function closeIfUnused(channel: string): void {
      if (broker.channels().includes(channel)) return;
      const ws = sockets.current.get(channel);
      // Delete from the map BEFORE closing so the close handler treats this as an
      // intentional teardown and does not schedule a reconnect.
      sockets.current.delete(channel);
      const timer = timers.current.get(channel);
      if (timer !== undefined) {
        clearTimeout(timer);
        timers.current.delete(channel);
      }
      attempts.current.delete(channel);
      // A deliberate teardown resets the replay cursor: a later re-subscribe is a
      // fresh first-connect (live tail), not a replay of everything since you left.
      lastSeq.current.delete(channel);
      if (ws) closeSocket(ws);
    }

    return {
      subscribe(channel, handler) {
        openForChannel(channel);
        const unsubscribe = broker.subscribe(channel, handler);
        return () => {
          unsubscribe();
          closeIfUnused(channel);
        };
      },
    };
  }, [broker, wsBase]);

  useEffect(() => {
    disposed.current = false;
    const open = sockets.current;
    const pending = timers.current;
    const counts = attempts.current;
    const seqs = lastSeq.current;
    return () => {
      disposed.current = true;
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
      open.forEach((ws) => closeSocket(ws));
      open.clear();
      counts.clear();
      seqs.clear();
    };
  }, []);

  return <WebSocketContext.Provider value={ctx}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): Ctx {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used inside WebSocketProvider");
  return ctx;
}
