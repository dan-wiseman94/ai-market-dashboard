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
  var_beta?: BookVarBeta;
}

/**
 * One point on the book's history curve.
 *
 * `GET /api/book/` serves a *trend* row, not the full X-ray: the per-position
 * arrays (exposures, clusters, VaR positions) are left to `GET /api/book/<id>/`.
 * Every metric is nullable — a day with no priceable position has no VaR, and a
 * zero there would invent a reading, so render a gap instead.
 */
export interface BookSnapshotTrend {
  id: number;
  created_at: string;
  as_of_date: string;
  hhi: number | null;
  top_n_share: number | null;
  total_abs: number | null;
  net_long: number | null;
  net_short: number | null;
  gross_dollar: number | null;
  net_dollar: number | null;
  diversified_var_usd: number | null;
  undiversified_var_usd: number | null;
  beta_adjusted_net_exposure_usd: number | null;
  regime: string | null;
  alignment: string | null;
  position_count: number;
  cluster_count: number;
  near_invalidation_count: number;
}

export const fetchCurrentBook = () => apiGet<BookSnapshot | null>("/api/book/current/");
/** Newest-first trend rows. `limit` is clamped server-side (default 90, max 730). */
export const fetchBookHistory = (limit = 30) =>
  apiGet<BookSnapshotTrend[]>(`/api/book/?limit=${limit}`);
/** Recompute the X-ray now (POST /api/book/recompute/) and return the fresh snapshot. */
export const recomputeBook = () => apiPost<BookSnapshot>("/api/book/recompute/");
