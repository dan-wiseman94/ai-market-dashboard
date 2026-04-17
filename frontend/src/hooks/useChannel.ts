import { useEffect } from "react";
import { useWebSocket } from "@/realtime/WebSocketProvider";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useChannel(channel: string | null, handler: (msg: any) => void): void {
  const ws = useWebSocket();
  useEffect(() => {
    if (!channel) return;
    const unsub = ws.subscribe(channel, handler);
    return unsub;
  }, [channel, handler, ws]);
}
