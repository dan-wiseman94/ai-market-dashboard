import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import { Broker } from "./subscriptions";

type Ctx = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  subscribe: (channel: string, handler: (msg: any) => void) => () => void;
};

const WebSocketContext = createContext<Ctx | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const broker = useMemo(() => new Broker(), []);
  const sockets = useRef(new Map<string, WebSocket>());

  const wsBase = import.meta.env.VITE_WS_BASE_URL ?? "";

  const openForChannel = (channel: string): WebSocket => {
    const existing = sockets.current.get(channel);
    if (existing) return existing;

    const path = channel.startsWith("thread.")
      ? `/ws/threads/${channel.slice("thread.".length)}/`
      : channel.startsWith("snapshot.")
      ? `/ws/snapshots/${channel.slice("snapshot.".length)}/`
      : null;
    if (!path) throw new Error(`Unknown channel: ${channel}`);

    const ws = new WebSocket(`${wsBase}${path}`);
    ws.addEventListener("message", (ev) => {
      try {
        broker.dispatch(channel, JSON.parse(ev.data));
      } catch { /* ignore malformed */ }
    });
    sockets.current.set(channel, ws);
    return ws;
  };

  const maybeClose = (channel: string) => {
    if (!broker.channels().includes(channel)) {
      sockets.current.get(channel)?.close();
      sockets.current.delete(channel);
    }
  };

  const ctx: Ctx = useMemo(() => ({
    subscribe: (channel, handler) => {
      openForChannel(channel);
      const unsubBroker = broker.subscribe(channel, handler);
      return () => {
        unsubBroker();
        maybeClose(channel);
      };
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), []);

  useEffect(() => {
    const current = sockets.current;
    return () => {
      current.forEach((ws) => ws.close());
      current.clear();
    };
  }, []);

  return <WebSocketContext.Provider value={ctx}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): Ctx {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used inside WebSocketProvider");
  return ctx;
}
