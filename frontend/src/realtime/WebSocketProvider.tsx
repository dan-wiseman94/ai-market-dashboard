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

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const broker = useMemo(() => new Broker(), []);
  const sockets = useRef(new Map<string, WebSocket>());
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
      sockets.current.set(channel, ws);
    }

    function closeIfUnused(channel: string): void {
      if (broker.channels().includes(channel)) return;
      sockets.current.get(channel)?.close();
      sockets.current.delete(channel);
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
    const open = sockets.current;
    return () => {
      open.forEach((ws) => ws.close());
      open.clear();
    };
  }, []);

  return <WebSocketContext.Provider value={ctx}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): Ctx {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used inside WebSocketProvider");
  return ctx;
}
