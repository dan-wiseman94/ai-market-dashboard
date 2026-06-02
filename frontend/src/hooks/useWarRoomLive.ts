import { useCallback, useMemo, useState } from "react";

import { useChannel } from "@/hooks/useChannel";

export type WarRoomLiveMessage = {
  id: number;
  text: string;
  status: "streaming" | "done" | "failed";
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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onWs = useCallback((msg: any) => {
    const id = msg.message_id;
    if (id == null) return;
    if (msg.event === "message_started") {
      setLive((prev) => ({ ...prev, [id]: { id, text: "", status: "streaming" } }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[id] ?? { id, text: "", status: "streaming" as const };
        return { ...prev, [id]: { ...cur, text: cur.text + (msg.text ?? "") } };
      });
    } else if (msg.event === "message_done") {
      setLive((prev) => ({
        ...prev,
        [id]: { ...(prev[id] ?? { id, text: "" }), status: "done" },
      }));
    } else if (msg.event === "error" || msg.event === "cost_capped") {
      setLive((prev) => ({
        ...prev,
        [id]: { ...(prev[id] ?? { id, text: "" }), status: "failed" },
      }));
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
