/**
 * Typed client for the Prediction Ledger (`/api/predictions/`).
 *
 * The row/rollup shapes come straight from the generated OpenAPI schema so a
 * backend contract change surfaces at type-check time rather than as an
 * `undefined` at runtime.
 *
 * `hit_rate` and `avg_forward_return_pct` are nullable **by design**: null means
 * "nothing decisive to score yet", never 0. Callers must render that distinction.
 */
import { apiGet } from "@/api/client";
import type { Schemas } from "@/api/generated";

export type AIPrediction = Schemas["AIPrediction"];
export type PredictionStatus = Schemas["AIPredictionStatusEnum"];
export type PredictionCounts = Schemas["PredictionCounts"];
export type PredictionTickerStats = Schemas["PredictionTickerStats"];
export type PredictionStats = Schemas["PredictionStats"];
export type PaginatedPredictions = Schemas["PaginatedAIPredictionList"];

export const PREDICTION_STATUSES: readonly PredictionStatus[] = [
  "open",
  "resolving",
  "resolved",
  "invalidated",
];

/** The ledger filters as the UI holds them. Every field is optional; a blank
 * one is simply not sent (the backend ignores unknown/blank values anyway). */
export interface PredictionQuery {
  ticker?: string;
  status?: PredictionStatus | "";
  horizon?: string;
  page?: number;
}

/** Serialize the filters into a query string, dropping blanks and page 1. */
export function predictionQueryString(q: PredictionQuery = {}): string {
  const params = new URLSearchParams();
  const ticker = (q.ticker ?? "").trim();
  if (ticker) params.set("ticker", ticker);
  if (q.status) params.set("status", q.status);
  const horizon = (q.horizon ?? "").trim();
  if (horizon) params.set("horizon", horizon);
  if (q.page !== undefined && q.page > 1) params.set("page", String(q.page));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** One page of the ledger, newest call first. */
export const fetchPredictions = (q: PredictionQuery = {}) =>
  apiGet<PaginatedPredictions>(`/api/predictions/${predictionQueryString(q)}`);

/** Counts + hit rate for the same cohort the list is showing. */
export const fetchPredictionStats = (q: PredictionQuery = {}) =>
  apiGet<PredictionStats>(`/api/predictions/stats/${predictionQueryString({ ...q, page: undefined })}`);

/** @public — one ledger row by id; the drill-down surface for a linked call. */
export const fetchPrediction = (id: number) => apiGet<AIPrediction>(`/api/predictions/${id}/`);
