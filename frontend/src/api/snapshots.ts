import { ApiError, apiGet, apiPost } from "./client";

export type SnapshotSection = {
  id: number; kind: string; status: "pending" | "done" | "failed";
  payload: unknown; error: string;
};

export type Snapshot = {
  id: number; profile_id: number; objective: string; notes: string;
  status: "pending" | "ready" | "failed";
  includes: string[]; source: string; captured_at: string;
  sections: SnapshotSection[];
};

export type CreateSnapshotBody = {
  profile_id: number;
  objective?: string;
  notes?: string;
  includes?: string[];
  watchlist_tickers?: string[];
  ohlc_ticker?: string;
  ohlc_timeframe?: string;
  ohlc_bars?: number;
  image_ids?: number[];
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
