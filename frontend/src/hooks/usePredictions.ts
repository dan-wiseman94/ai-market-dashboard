import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/api/client";
import {
  fetchPrediction,
  fetchPredictionStats,
  fetchPredictions,
  type PredictionQuery,
} from "@/api/predictions";

/** One page of the Prediction Ledger under the current filters.
 *
 * `keepPreviousData` keeps the previous page on screen while the next one
 * loads, so paging/filtering doesn't flash the whole table back to a skeleton. */
export function usePredictionLedger(query: PredictionQuery) {
  return useQuery({
    queryKey: ["predictions/list", query],
    queryFn: () => fetchPredictions(query),
    placeholderData: keepPreviousData,
  });
}

/** Counts + hit rate over the same cohort the ledger list is showing. */
export function usePredictionStats(query: PredictionQuery) {
  return useQuery({
    queryKey: ["predictions/stats", { ...query, page: undefined }],
    queryFn: () => fetchPredictionStats(query),
    placeholderData: keepPreviousData,
  });
}

/** @public — a single ledger row by id (drill-down from a linked call). */
export function usePrediction(id: number | null) {
  return useQuery({
    queryKey: ["predictions/detail", id],
    queryFn: () => fetchPrediction(id as number),
    enabled: id !== null,
  });
}

export interface AIView {
  ticker: string;
  has_view: boolean;
  direction?: string;
  confidence?: number;
  horizon_days?: number;
  predicted_at?: string;
  rationale?: string;
  provider?: string;
  model?: string;
  agreement?: "agree" | "diverge" | "partial" | null;
}

/** The AI's current live call on a ticker, reconciled against a thesis direction. */
export function useAIView(ticker: string, against?: string) {
  return useQuery({
    queryKey: ["predictions/ai-view", ticker, against ?? null],
    queryFn: () => {
      const a = against ? `&against=${encodeURIComponent(against)}` : "";
      return apiGet<AIView>(`/api/predictions/ai-view/?ticker=${encodeURIComponent(ticker)}${a}`);
    },
    enabled: !!ticker,
  });
}

export interface Divergence {
  thesis_id: number;
  ticker: string;
  title: string;
  thesis_direction: string;
  conviction: number;
  ai_direction: string;
  ai_confidence: number;
  ai_horizon_days: number;
  agreement: "diverge" | "partial";
}

export interface DivergencesResponse {
  count: number;
  rows: Divergence[];
}

/** Open theses that conflict with the AI's current call (dashboard rollup). */
export function useDivergences() {
  return useQuery({
    queryKey: ["predictions/divergences"],
    queryFn: () => apiGet<DivergencesResponse>("/api/predictions/divergences/"),
  });
}
