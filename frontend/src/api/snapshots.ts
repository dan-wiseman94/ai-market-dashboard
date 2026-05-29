import { ApiError, apiGet, apiPost } from "./client";

export type SnapshotSection = {
  id: number; kind: string; status: "pending" | "done" | "failed";
  payload: unknown; error: string;
};

export type Snapshot = {
  id: number; profile_id: number; objective: string; notes: string;
  manual_positions: string;
  status: "pending" | "ready" | "failed";
  includes: string[]; source: string; captured_at: string;
  overnight: boolean;
  sections: SnapshotSection[];
};

export type CreateSnapshotBody = {
  profile_id: number;
  objective?: string;
  notes?: string;
  manual_positions?: string;
  includes?: string[];
  watchlist_tickers?: string[];
  ohlc_ticker?: string;
  ohlc_timeframe?: string;
  ohlc_bars?: number;
  image_ids?: number[];
  overnight?: boolean;
};

export const createSnapshot = (body: CreateSnapshotBody) =>
  apiPost<Snapshot>("/api/snapshots/", body);

export const fetchSnapshot = (id: number) => apiGet<Snapshot>(`/api/snapshots/${id}/`);

/**
 * Poll a snapshot until capture reaches a terminal status.
 *
 * `createSnapshot` returns HTTP 202 with status="pending" because capture runs
 * asynchronously in a Celery worker. Callers that need a ready snapshot — e.g.
 * pinning it to a thread — must wait, since the thread-create endpoint rejects a
 * non-ready snapshot with 400 ("Snapshot is not ready").
 *
 * Resolves with the ready Snapshot. Throws ApiError if capture failed
 * (`snapshot_failed`) or did not finish within `timeoutMs` (`snapshot_timeout`).
 * `fetch` is injectable for tests.
 */
export async function waitForSnapshotReady(
  id: number,
  {
    intervalMs = 600,
    timeoutMs = 120_000,
    fetch = fetchSnapshot,
  }: {
    intervalMs?: number;
    timeoutMs?: number;
    fetch?: (id: number) => Promise<Snapshot>;
  } = {},
): Promise<Snapshot> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const snap = await fetch(id);
    if (snap.status === "ready") return snap;
    if (snap.status === "failed") {
      throw new ApiError(400, "snapshot_failed", "Snapshot capture failed");
    }
    if (Date.now() >= deadline) {
      throw new ApiError(504, "snapshot_timeout", "Snapshot capture timed out");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export type SnapshotDiff = { delta: string; prev_id: number; curr_id: number };
export const fetchSnapshotDiff = (id: number, against?: number) => {
  const q = against ? `?against=${against}` : "";
  return apiGet<SnapshotDiff>(`/api/snapshots/${id}/diff/${q}`);
};

export type SnapshotListRow = {
  id: number; captured_at: string; profile_id: number; profile_name: string;
  objective: string; status: string; source: string; primary_ticker: string | null;
  section_kinds: string[]; section_statuses: Record<string, string>;
  has_image: boolean; total_payload_tokens: number; headline_delta_pct?: number | null;
  overnight: boolean;
};
export const fetchSnapshots = (params: Record<string, string> = {}) =>
  apiGet<{ results: SnapshotListRow[]; count?: number }>(
    `/api/snapshots/?${new URLSearchParams(params)}`);
export const fetchSnapshotTimeline = (ticker: string) =>
  apiGet<{ results: SnapshotListRow[] }>(`/api/snapshots/timeline/?ticker=${encodeURIComponent(ticker)}`);
export const explainDiff = (id: number, against?: number) =>
  apiPost<{ thread_id: number; message_id: number; delta: string }>(
    `/api/snapshots/${id}/explain-diff/`, against ? { against } : {});
