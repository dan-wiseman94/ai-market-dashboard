import { apiGet } from "./client";

export type ProviderCost = {
  provider: string; cost_usd: string; runs: number;
  input_tokens: number; output_tokens: number; cached_tokens: number;
};
export type CostsToday = { total_usd: string; by_provider: ProviderCost[] };

export const fetchCostsToday = () => apiGet<CostsToday>("/api/costs/today/");
