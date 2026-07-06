import { useEffect, useRef } from "react";
import { useWebSocket } from "@/realtime/WebSocketProvider";

/**
 * Subscribe to a realtime channel for the lifetime of the component.
 *
 * The handler is held in a ref, so its identity is deliberately NOT an effect
 * dependency: an inline (unmemoized) handler at a call site must not tear the
 * WebSocket down and reopen it on every render — a sole-subscriber teardown
 * also drops the channel's replay cursor (WebSocketProvider.closeIfUnused),
 * silently defeating the `?since=` replay on the next connect. The
 * subscription is keyed on the channel name only; the latest handler always
 * receives the messages.
 */
export function useChannel<T = unknown>(
  channel: string | null,
  handler: (msg: T) => void,
): void {
  const ws = useWebSocket();
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });
  useEffect(() => {
    if (!channel) return;
    const unsub = ws.subscribe(channel, (msg) => handlerRef.current(msg as T));
    return unsub;
  }, [channel, ws]);
}
