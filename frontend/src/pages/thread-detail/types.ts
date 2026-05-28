/** Shared types for the ThreadDetailPage subtree. */

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
};

// WebSocket messages on the thread channel are an open event union; the
// consumer narrows on `event` at runtime.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WsMsg = any;
