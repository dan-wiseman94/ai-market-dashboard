/** Shared types for the ThreadDetailPage subtree. */
import type {
  StructuredKind, StructuredReport, WarRoomVerdictContent,
} from "@/api/observation";
import type { CitationRef } from "@/components/CitationText";
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
  // Citations the model attached while streaming. Accumulated from the WS
  // `citation` frames — the persisted Message row does not carry them, so a
  // reseed preserves whatever the live stream collected.
  citations?: CitationRef[];
};

// WebSocket messages on the thread channel: the normalized closed event union
// the backend broadcasts. Handlers narrow on `event` (or `type` for the
// seq-less replay_gap frame).
export type WsMsg = ThreadWsMsg;
