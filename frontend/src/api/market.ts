import { apiGet, apiPost, apiDelete } from "./client";

export type Quote = {
  last: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  high: number | null;
  low: number | null;
  pct_change: number | null;
};

export type OhlcBar = {
  ts: string; open: number; high: number; low: number; close: number; volume: number;
};

export type Position = {
  ticker: string; qty: number; avg_cost: number | null; mkt_value: number | null;
  unrealized_pl: number | null; day_pl: number | null;
};

export type MarketContext = {
  spy_last: number | null; qqq_last: number | null; vix_last: number | null;
  sectors: Record<string, number | null>;
  breadth: Record<string, number | null>;
};

export const fetchQuotes = (tickers: string[]) =>
  apiGet<Record<string, Quote>>(`/api/market/quotes/?tickers=${encodeURIComponent(tickers.join(","))}`);

export const fetchOhlc = (ticker: string, timeframe: string, bars = 60) =>
  apiGet<{ ticker: string; timeframe: string; bars: OhlcBar[] }>(
    `/api/market/ohlc/?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&bars=${bars}`,
  );

export const fetchPositions = () => apiGet<Position[]>("/api/market/positions/");
export const fetchMarketContext = () => apiGet<MarketContext>("/api/market/context/");

export type MarketKey =
  | "us_equity" | "us_bond" | "cme_futures" | "cfe_futures" | "crypto" | "lse" | "jpx";

export interface CalendarOverride {
  id: number;
  symbol: string;
  market_key: MarketKey;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface CalendarMarketStatus {
  is_open: boolean;
  phase: string;
  is_early_close: boolean;
  next_open: string | null;
  next_close: string | null;
}

export const listCalendarOverrides = () =>
  apiGet<CalendarOverride[]>("/api/market/calendar-overrides/");
export const createCalendarOverride = (body: { symbol: string; market_key: MarketKey; note?: string }) =>
  apiPost<CalendarOverride>("/api/market/calendar-overrides/", body);
export const deleteCalendarOverride = (id: number) =>
  apiDelete(`/api/market/calendar-overrides/${id}/`);

export const getCalendarStatus = (symbols: string[] = []) => {
  const qs = symbols.map((s) => `symbol=${encodeURIComponent(s)}`).join("&");
  return apiGet<{ markets: Record<string, CalendarMarketStatus> }>(
    `/api/market/calendar-status/${qs ? `?${qs}` : ""}`,
  );
};
