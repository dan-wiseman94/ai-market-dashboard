import { useCallback, useMemo, useState } from "react";

import { useChannel } from "@/hooks/useChannel";
import type { ThreadWsMsg } from "@/realtime/threadEvents";

export type WarRoomLiveMessage = {
  id: number;
  text: string;
  status: "streaming" | "done" | "failed";
};

// Terminal lifecycle events → the status they settle an in-flight message into.
const TERMINAL_STATUS: Record<string, "done" | "failed"> = {
  message_done: "done",
  error: "failed",
  cost_capped: "failed",
};

/**
 * Live persona-token stream for a running War Room debate. The personas run
 * through `run_ai_on_message`, which already broadcasts message_started /
 * text_delta / message_done over `thread.<thread_id>`; this hook accumulates
 * those into ordered, in-flight messages so the courtroom can render the
 * argument as it is written. Disabled (no subscription) once the run is done.
 */
export function useWarRoomLive(threadId: number | null, enabled: boolean) {
  const [live, setLive] = useState<Record<number, WarRoomLiveMessage>>({});

  const onWs = useCallback((msg: ThreadWsMsg) => {
    const id = msg.message_id;
    if (id == null) return;
    if (msg.event === "message_started") {
      setLive((prev) => ({ ...prev, [id]: { id, text: "", status: "streaming" } }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[id] ?? { id, text: "", status: "streaming" as const };
        return { ...prev, [id]: { ...cur, text: cur.text + msg.text } };
      });
    } else {
      const status = msg.event ? TERMINAL_STATUS[msg.event] : undefined;
      if (status) {
        setLive((prev) => ({
          ...prev,
          [id]: { ...(prev[id] ?? { id, text: "" }), status },
        }));
      }
    }
  }, []);

  useChannel(enabled && threadId ? `thread.${threadId}` : null, onWs);

  const messages = useMemo(
    () => Object.values(live).sort((a, b) => a.id - b.id),
    [live],
  );
  const streaming = messages.some((m) => m.status === "streaming");
  return { messages, streaming };
}
