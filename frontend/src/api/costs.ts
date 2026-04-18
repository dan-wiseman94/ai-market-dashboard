import { apiGet } from "./client";

export type ProviderCost = {
  provider: string; cost_usd: string; runs: number;
  input_tokens: number; output_tokens: number; cached_tokens: number;
};
export type CostsToday = { total_usd: string; by_provider: ProviderCost[] };

export const fetchCostsToday = () => apiGet<CostsToday>("/api/costs/today/");

export type CostsSummary = {
  total: string;
  by_provider: Array<{ provider: string; cost_usd: string; runs: number;
    input_tokens: number; output_tokens: number; cached_tokens: number }>;
  by_model: Array<{ provider: string; model: string; cost_usd: string; runs: number;
    input_tokens: number; output_tokens: number; cached_tokens: number }>;
  by_thread: Array<{ thread_id: number; title: string; cost_usd: string; runs: number }>;
  daily: Array<{ date: string; cost_usd: string; runs: number }>;
};

export type CapRow = {
  provider: string;
  daily: { cap: string; spent: string; pct: number };
  monthly: { cap: string; spent: string; pct: number } | null;
};

export type SnapshotBreakdownRow = {
  section: string;
  payload_tokens: number;
  cost_share_usd: string;
};

export const fetchCostsSummary = (range: { from: string; to: string }) =>
  apiGet<CostsSummary>(`/api/costs/summary?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`);

export const fetchCostsCaps = () => apiGet<CapRow[]>("/api/costs/caps");

export const fetchCostsSnapshot = (snapshotId: number) =>
  apiGet<SnapshotBreakdownRow[]>(`/api/costs/snapshot/${snapshotId}`);
