import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type WatchlistSymbol = { id: number; ticker: string; sort_order: number };
export type Watchlist = { id: number; name: string; created_at: string; symbols: WatchlistSymbol[] };

export const fetchWatchlists = () => apiGet<Watchlist[]>("/api/watchlists/");
export const fetchWatchlist = (id: number) => apiGet<Watchlist>(`/api/watchlists/${id}/`);
export const createWatchlist = (name: string) =>
  apiPost<Watchlist>("/api/watchlists/", { name });
export const renameWatchlist = (id: number, name: string) =>
  apiPatch<Watchlist>(`/api/watchlists/${id}/`, { name });
export const deleteWatchlist = (id: number) => apiDelete(`/api/watchlists/${id}/`);
export const addSymbol = (wid: number, ticker: string) =>
  apiPost<WatchlistSymbol>(`/api/watchlists/${wid}/symbols/`, { ticker });
export const removeSymbol = (wid: number, sid: number) =>
  apiDelete(`/api/watchlists/${wid}/symbols/${sid}/`);
export const reorderSymbols = (wid: number, order: number[]) =>
  apiPost<{ ok: boolean }>(`/api/watchlists/${wid}/reorder/`, { order });
