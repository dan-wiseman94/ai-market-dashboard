import { apiGet, apiPost } from "@/api/client";

export interface BookExposure {
  ticker: string;
  net_signed: number;
  abs_exposure: number;
  dollar: number | null;
  sources: string[];
}
export interface BookCluster { members: string[]; avg_corr: number | null }
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
}

export const fetchCurrentBook = () => apiGet<BookSnapshot | null>("/api/book/current/");
export const fetchBookHistory = () => apiGet<BookSnapshot[]>("/api/book/");
export const recomputeBook = () => apiPost<BookSnapshot>("/api/book/recompute/");
