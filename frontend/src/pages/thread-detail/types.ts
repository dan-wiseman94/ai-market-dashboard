/** Shared types for the ThreadDetailPage subtree. */
import type {
  StructuredKind, StructuredReport, WarRoomVerdictContent,
} from "@/api/observation";
import type { ThreadWsMsg } from "@/realtime/threadEvents";

export type LiveMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  status: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
  provider?: string;
  parent_message_id?: number | null;
  // Present only on the synthetic snapshot turn; drives the collapsible payload box.
  snapshot_id?: number | null;
  // Present on the typed messages the backend writes (observer cards, post-mortems,
  // war-room verdicts, cached/warning/investigation notices).
  kind?: StructuredKind;
  report?: StructuredReport;
  verdict?: WarRoomVerdictContent;
};

// WebSocket messages on the thread channel: the normalized closed event union
// the backend broadcasts. Handlers narrow on `event` (or `type` for the
// seq-less replay_gap frame).
export type WsMsg = ThreadWsMsg;
