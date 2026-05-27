/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import { Broker } from "./subscriptions";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Handler = (msg: any) => void;
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
  throw new Error(`Unknown channel: ${channel}`);
}

const WS_CONNECTING = 0;

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

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const broker = useMemo(() => new Broker(), []);
  const sockets = useRef(new Map<string, WebSocket>());
  // Pending reconnect timers and per-channel backoff attempt counts.
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const attempts = useRef(new Map<string, number>());
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
      const ws = new WebSocket(`${wsBase}${pathForChannel(channel)}`);
      ws.addEventListener("message", (ev) => {
        try {
          broker.dispatch(channel, JSON.parse(ev.data));
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
    return () => {
      disposed.current = true;
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
      open.forEach((ws) => closeSocket(ws));
      open.clear();
      counts.clear();
    };
  }, []);

  return <WebSocketContext.Provider value={ctx}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): Ctx {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used inside WebSocketProvider");
  return ctx;
}
