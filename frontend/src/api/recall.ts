import { apiGet } from "./client";

export interface RecallHit {
  kind: string;
  object_id: number;
  snippet: string;
  link: string;
  source_created_at: string | null;
  tickers: string[];
}

export interface RecallResult {
  results: RecallHit[];
  mode: "semantic" | "keyword";
}

export interface RecallSearchParams {
  q: string;
  k?: number;
  kind?: string;
  ticker?: string;
}

export interface RecallRelatedParams {
  kind: string;
  id: number;
  k?: number;
}

export interface RecallStatus {
  /** Per-kind indexed-document counts, plus a "total" key. */
  counts: Record<string, number>;
  mode: "semantic" | "keyword";
}

export function recallSearch(params: RecallSearchParams): Promise<RecallResult> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.k != null) qs.set("k", String(params.k));
  if (params.kind) qs.set("kind", params.kind);
  if (params.ticker) qs.set("ticker", params.ticker);
  return apiGet<RecallResult>(`/api/recall/?${qs.toString()}`);
}

export function recallRelated(params: RecallRelatedParams): Promise<RecallResult> {
  const qs = new URLSearchParams();
  qs.set("kind", params.kind);
  qs.set("id", String(params.id));
  if (params.k != null) qs.set("k", String(params.k));
  return apiGet<RecallResult>(`/api/recall/related/?${qs.toString()}`);
}

export function recallStatus(): Promise<RecallStatus> {
  return apiGet<RecallStatus>("/api/recall/status/");
}
