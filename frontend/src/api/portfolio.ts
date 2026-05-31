import { apiDelete, apiGet, apiPost } from "./client";

// DRF DecimalField serialises to string — all decimal-typed fields arrive as strings.
export type PositionDirection = "long" | "short";
export type PositionStatus = "open" | "closed";

export interface PositionUnrealized {
  last: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pct: number | null;
}

export interface PortfolioPosition {
  id: number;
  ticker: string;
  direction: PositionDirection;
  quantity: string; // DRF DecimalField → string
  avg_cost: string; // DRF DecimalField → string
  opened_at: string;
  closed_at: string | null;
  close_price: string | null; // DRF DecimalField → string
  realized_pnl: string | null; // DRF DecimalField → string
  status: PositionStatus;
  note: string;
  thesis_id: number | null;
  profile_id: number | null;
  unrealized: PositionUnrealized | null;
  created_at: string;
  updated_at: string;
}

export interface ListPositionsParams {
  status?: PositionStatus;
  ticker?: string;
  thesis?: number;
}

export interface CreatePositionBody {
  ticker: string;
  direction: PositionDirection;
  quantity: string;
  avg_cost: string;
  opened_at?: string;
  note?: string;
  thesis_id?: number | null;
  profile_id?: number | null;
}

export interface ClosePositionBody {
  close_price: string;
  closed_at?: string;
}

export function listPositions(params?: ListPositionsParams): Promise<PortfolioPosition[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.ticker) qs.set("ticker", params.ticker);
  if (params?.thesis != null) qs.set("thesis", String(params.thesis));
  const query = qs.toString();
  return apiGet<PortfolioPosition[]>(`/api/portfolio/positions/${query ? `?${query}` : ""}`);
}

export function createPosition(body: CreatePositionBody): Promise<PortfolioPosition> {
  return apiPost<PortfolioPosition>("/api/portfolio/positions/", body);
}

export function closePosition(id: number, body: ClosePositionBody): Promise<PortfolioPosition> {
  return apiPost<PortfolioPosition>(`/api/portfolio/positions/${id}/close/`, body);
}

export function deletePosition(id: number): Promise<void> {
  return apiDelete(`/api/portfolio/positions/${id}/`);
}
