import { apiGet, apiPatch, apiPost } from "./client";
import type { ObservationReport } from "@/components/ObservationReportCard";

export type AiRun = {
  id: number; provider: string; model: string;
  input_tokens: number; output_tokens: number; cached_tokens: number;
  cost_usd: string; latency_ms: number;
  status: "pending" | "streaming" | "done" | "failed" | "cost_capped";
  error: string;
};

export type Message = {
  id: number;
  role: "user" | "assistant" | "system";
  content: {
    text?: string;
    kind?: "structured_observation";
    report?: ObservationReport;
  };
  status: "done" | "streaming" | "failed";
  error: string;
  created_at: string;
  ai_run?: AiRun | null;
  // Set on the synthetic snapshot turn (the pinned-snapshot user message).
  snapshot_id?: number | null;
};

export type Thread = {
  id: number; kind: "consult" | "chat" | "observer"; title: string;
  profile: { id: number; name: string; default_provider: string; default_model: string } | null;
  pinned_snapshot_id: number | null;
  created_at: string;
  messages: Message[];
};

export const fetchThreads = () => apiGet<Thread[]>("/api/threads/");
export const fetchThread = (id: number) => apiGet<Thread>(`/api/threads/${id}/`);

export const createThread = (body: {
  kind: "consult" | "chat"; profile_id?: number; pinned_snapshot_id?: number; title?: string;
  // When true alongside a pinned snapshot, the backend immediately streams an AI
  // reply to the snapshot (the "ask" half of "Capture + ask").
  auto_reply?: boolean;
}) => apiPost<Thread>("/api/threads/", body);

export const sendMessage = (
  threadId: number,
  text: string,
  override?: { provider: string; model: string },
) =>
  apiPost<Message>(`/api/threads/${threadId}/send/`, {
    text,
    override_provider: override?.provider,
    override_model: override?.model,
  });

export const compareMessage = (threadId: number, text: string, branches: {provider: string; model: string}[]) =>
  apiPost<{ user_message_id: number; branches: { provider: string; model: string; task_id: string }[] }>(
    `/api/threads/${threadId}/compare/`, { text, branches },
  );

export const stopMessage = (threadId: number, messageId: number) =>
  apiPost<{ ok: boolean }>(`/api/threads/${threadId}/stop/${messageId}/`);

export const renameThread = (threadId: number, title: string) =>
  apiPatch<Thread>(`/api/threads/${threadId}/`, { title });
