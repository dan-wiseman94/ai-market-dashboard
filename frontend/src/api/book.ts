import { apiGet, apiPost } from "@/api/client";

export interface BookExposure {
  ticker: string;
  net_signed: number;
  abs_exposure: number;
  dollar: number | null;
  sources: string[];
}
export interface BookCluster { members: string[]; avg_corr: number | null }
export interface BookVarPosition {
  ticker: string;
  dollar: number;
  daily_vol_pct: number;
  var_usd: number;
  beta: number | null;
}
export interface BookVarBeta {
  available: boolean;
  method: string;
  window: number;
  positions: BookVarPosition[];
  portfolio: {
    gross_dollar?: number;
    net_dollar?: number;
    undiversified_var_usd?: number;
    diversified_var_usd?: number;
    diversification_benefit_usd?: number;
    beta_adjusted_net_exposure_usd?: number;
    n_positions?: number;
  };
  skipped?: number;
  note?: string;
}
export interface BookSnapshot {
  id: number;
  created_at: string;
  as_of_date: string;
  exposures: BookExposure[];
  concentration: { total_abs?: number; top_n_share?: number; net_long?: number; net_short?: number; hhi?: number };
  clusters: BookCluster[];
  regime_fit: { regime?: string | null; alignment?: string; note?: string };
  near_invalidation: { ticker: string; pct_to_invalidation: number }[];
  narrative: string;
  coverage: Record<string, number>;
  var_beta?: BookVarBeta;
}

export const fetchCurrentBook = () => apiGet<BookSnapshot | null>("/api/book/current/");
export const fetchBookHistory = () => apiGet<BookSnapshot[]>("/api/book/");
/** @public — typed client for POST /api/book/recompute/; awaits a UI "recompute" affordance. */
export const recomputeBook = () => apiPost<BookSnapshot>("/api/book/recompute/");
