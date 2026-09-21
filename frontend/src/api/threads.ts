import { apiDelete, apiGet, apiPatch, apiPost, apiPostForm } from "./client";
import type { Schemas } from "./generated";
import type { ObservationReport } from "./observation";

export type AiRun = {
  id: number; provider: string; model: string;
  input_tokens: number; output_tokens: number; cached_tokens: number;
  cost_usd: string; latency_ms: number;
  status: "pending" | "streaming" | "done" | "failed" | "cost_capped";
  error: string;
};

// The `*_id` FK surface + role/created_at are sourced from the generated OpenAPI
// schema (api/generated.ts → schema.d.ts, drift-gated in CI) so backend contract
// drift on these fields is caught at type-check time rather than silently read as
// `undefined` (the exact *_id landmine CLAUDE.md flags). content/status/ai_run
// keep the hand-written precise shapes the UI relies on — the generated schema
// types `content` as `unknown` and `ai_run` as a non-null AIRun.
export type Message = Pick<
  Schemas["Message"],
  "id" | "role" | "created_at" | "parent_message_id" | "snapshot_id"
> & {
  content: {
    text?: string;
    kind?: "structured_observation";
    report?: ObservationReport;
  };
  status: "done" | "streaming" | "failed";
  error: string;
  ai_run?: AiRun | null;
};

export type ThreadProfile = {
  id: number; name: string; default_provider: string; default_model: string;
} | null;

export type Thread = {
  id: number; kind: "consult" | "chat" | "observer"; title: string;
  profile: ThreadProfile;
  pinned_snapshot_id: number | null;
  created_at: string;
  messages: Message[];
};

// Light row from the list endpoint — no per-thread messages (see backend
// ThreadListSerializer); carries message_count instead. The detail view
// (fetchThread) still returns the full Thread with nested messages.
export type ThreadListRow = {
  id: number; kind: "consult" | "chat" | "observer"; title: string;
  profile: ThreadProfile;
  pinned_snapshot_id: number | null;
  created_at: string;
  message_count: number;
};

// The list endpoint is paginated (LimitOffsetPagination); unwrap to the rows.
export const fetchThreads = () =>
  apiGet<{ results: ThreadListRow[]; count?: number }>("/api/threads/").then((r) => r.results);

export type ThreadPage = {
  results: ThreadListRow[];
  count: number;
  next: string | null;
  previous: string | null;
};

// Paginated fetch for the list UI — offset/limit so older threads are reachable
// (the bare fetchThreads above only ever returns the newest page).
export const fetchThreadsPage = (params?: { limit?: number; offset?: number }) => {
  const sp = new URLSearchParams({ limit: String(params?.limit ?? 50) });
  if (params?.offset) sp.set("offset", String(params.offset));
  return apiGet<ThreadPage>(`/api/threads/?${sp.toString()}`);
};
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

// ---------------------------------------------------------------------------
// Files — apps.threads.UserFile, a thin proxy over the Anthropic Files API.
// The bytes never live locally: upload streams straight through and a delete
// removes the upstream object too. Claude-only (documents are stripped from a
// non-Claude request, which warns via the capability_warning path).
// ---------------------------------------------------------------------------

export type UserFile = {
  id: number;
  anthropic_id?: string;
  kind: string;
  ticker: string;
  mime: string;
  size: number;
  filename: string;
};

export type FileKind = Schemas["UserFileKindEnum"];

/** The upload kinds the backend accepts. `satisfies` pins the list to the
 * generated enum, so a backend rename reds type-check instead of silently
 * offering a kind the serializer rejects. */
export const FILE_KINDS = [
  "filing",
  "transcript",
  "ohlc_csv",
  "research",
  "other",
] as const satisfies readonly FileKind[];

/** Error code the upload endpoint returns with HTTP 413 when the file exceeds
 * the server's per-upload ceiling (AI_FILE_UPLOAD_MAX_BYTES, 32MB default). */
export const FILE_TOO_LARGE_CODE = "file_too_large";

// The list endpoint wraps its rows in {results: [...]}; unwrap to the rows.
export const fetchFiles = (kind?: string) => {
  const params = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return apiGet<{ results?: UserFile[] } | null>(`/api/files/${params}`).then(
    (body) => body?.results ?? [],
  );
};

// Multipart: `file` plus the optional `kind`/`ticker` fields.
export const uploadFile = (form: FormData) => apiPostForm<UserFile>("/api/files/", form);

// Also deletes the upstream object at the provider (Anthropic Files API).
export const deleteFile = (id: number) => apiDelete(`/api/files/${id}/`);

export const attachFileToThread = (threadId: number, body: { file_id: number; prompt: string }) =>
  apiPost<{ message_id: number }>(`/api/threads/${threadId}/attach-file/`, body);
