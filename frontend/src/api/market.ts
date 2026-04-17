import { apiGet } from "./client";

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
