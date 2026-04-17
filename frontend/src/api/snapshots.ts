import { apiGet, apiPost } from "./client";

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
