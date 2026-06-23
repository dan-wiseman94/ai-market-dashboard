import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/api/client";

export interface LeaderboardRow {
  provider: string;
  model: string;
  runs: number;
  total_cost_usd: string;
  avg_latency_ms: number;
  avg_forward_return_pct: number | null;
  coverage_pct: number;
}

export interface CostPerInsight {
  total_cost_usd: string;
  threads_with_ai: number;
  snapshots_with_ai: number;
  trigger_fires: number;
  insights: number;
  cost_per_insight_usd: string | null;
}

export interface HeatmapCell {
  weekday: number;
  hour: number;
  count: number;
}

export interface TimelineDay {
  date: string;
  success: number;
  failed: number;
  skipped: number;
}

export interface UnusualRow {
  strike: string;
  side: "call" | "put";
  expiry: string;
  volume: number;
  oi: number;
  iv: number | null;
  volume_ratio: number;
  iv_z: number | null;
  triggers: string[];
  score: number;
}

function startISO(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

export function useLeaderboard(days = 30, forwardHours = 24) {
  return useQuery({
    queryKey: ["analytics/leaderboard", days, forwardHours],
    queryFn: () =>
      apiGet<{ rows: LeaderboardRow[] }>(
        `/api/analytics/leaderboard/?forward_hours=${forwardHours}` +
          `&start=${startISO(days)}`,
      ),
  });
}

export function useCostPerInsight(days = 30) {
  return useQuery({
    queryKey: ["analytics/cpi", days],
    queryFn: () =>
      apiGet<CostPerInsight>(
        `/api/analytics/cost-per-insight/?start=${startISO(days)}`,
      ),
  });
}

export function useTriggerHeatmap(days = 30) {
  return useQuery({
    queryKey: ["analytics/trigger-heatmap", days],
    queryFn: () =>
      apiGet<{ cells: HeatmapCell[] }>(
        `/api/analytics/trigger-heatmap/?start=${startISO(days)}`,
      ),
  });
}

export function useObserverTimeline(days = 30) {
  return useQuery({
    queryKey: ["analytics/observer-timeline", days],
    queryFn: () =>
      apiGet<{ days: TimelineDay[] }>(
        `/api/analytics/observer-timeline/?start=${startISO(days)}`,
      ),
  });
}

export function useUnusualOptions(ticker: string) {
  return useQuery({
    queryKey: ["analytics/unusual-options", ticker],
    queryFn: () =>
      apiGet<{ rows: UnusualRow[] }>(
        `/api/analytics/unusual-options/?ticker=${encodeURIComponent(ticker)}`,
      ),
    enabled: !!ticker,
  });
}

export interface CalibrationBucket {
  conviction: number;
  n: number;
  correct: number;
  incorrect: number;
  mixed: number;
  inconclusive: number;
  hit_rate: number | null;
}

export interface CalibrationOverall {
  scored: number;
  hit_rate: number | null;
  correct: number;
  incorrect: number;
  mixed: number;
  inconclusive: number;
  avg_forward_return_pct: number | null;
}

export interface ProviderCalibrationRow {
  provider: string;
  model: string;
  n: number;
  correct: number;
  incorrect: number;
  hit_rate: number | null;
}

export interface Calibration {
  horizon: number;
  scored: number;
  attributable: number;
  thesis: {
    buckets: CalibrationBucket[];
    brier: number | null;
    prob_map: Record<string, number>;
    overall: CalibrationOverall;
    by_direction: Record<string, { n: number; hit_rate: number | null }>;
  };
  provider: ProviderCalibrationRow[];
}

export function useCalibration(days = 90, horizon = 30) {
  return useQuery({
    queryKey: ["analytics/calibration", days, horizon],
    queryFn: () =>
      apiGet<Calibration>(
        `/api/analytics/calibration/?horizon=${horizon}&start=${startISO(days)}`,
      ),
  });
}

export interface CalibrationDrilldownRow {
  thesis_id: number;
  title: string;
  ticker: string;
  direction: string;
  conviction: number;
  verdict: string;
  forward_return_pct: number;
  horizon_days: number;
  completed_at: string | null;
  thread_id: number | null;
}

export interface CalibrationDrilldown {
  start: string;
  end: string;
  horizon: number;
  count: number;
  filters: { conviction: number | null; direction: string | null; verdict: string | null };
  rows: CalibrationDrilldownRow[];
}

/** Theses behind one calibration bucket. Disabled until a conviction is picked. */
export function useCalibrationDrilldown(conviction: number | null, horizon = 30, days = 90) {
  return useQuery({
    queryKey: ["analytics/calibration/drilldown", conviction, horizon, days],
    queryFn: () =>
      apiGet<CalibrationDrilldown>(
        `/api/analytics/calibration/drilldown/?conviction=${conviction}&horizon=${horizon}&start=${startISO(days)}`,
      ),
    enabled: conviction !== null,
  });
}

export interface AIReliabilityBand {
  band: string;
  n: number;
  correct: number;
  incorrect: number;
  mean_confidence: number;
  observed_hit_rate: number | null;
}

export interface AICalibration {
  start: string;
  end: string;
  horizon: number | null;
  overall: {
    scored: number;
    hit_rate: number | null;
    correct: number;
    incorrect: number;
    mixed: number;
  };
  brier: number | null;
  reliability: AIReliabilityBand[];
  by_provider_model: ProviderCalibrationRow[];
  by_direction: Record<string, { n: number; hit_rate: number | null }>;
  // #13: how often the actual move beat the options-priced 1σ move.
  beat_the_straddle?: {
    n: number;
    beyond_priced: number;
    within_priced: number;
    beyond_rate: number | null;
    edge_rate: number | null;
  };
}

/** Live calibration of the AI's OWN resolved predictions (M13). */
export function useAICalibration(days = 90, horizon?: number) {
  const h = horizon != null ? `&horizon=${horizon}` : "";
  return useQuery({
    queryKey: ["analytics/ai-calibration", days, horizon ?? null],
    queryFn: () =>
      apiGet<AICalibration>(`/api/analytics/ai-calibration/?start=${startISO(days)}${h}`),
  });
}

export interface CalibrationDriftModel {
  model: string;
  recent_error: number | null;
  baseline_error: number | null;
  delta: number | null;
  drifting: boolean;
  direction: "overconfident" | "underconfident" | "stable";
  status: "scored" | "insufficient_history";
  recent_runs: number;
  baseline_runs: number;
}
export interface CalibrationDrift {
  generated_at: string;
  window_days: number;
  models: CalibrationDriftModel[];
}

/** #14 — per-model calibration drift (recent vs baseline EvalRun error). */
export function useCalibrationDrift(windowDays = 30) {
  return useQuery({
    queryKey: ["analytics/calibration-drift", windowDays],
    queryFn: () =>
      apiGet<CalibrationDrift>(`/api/analytics/calibration-drift/?window_days=${windowDays}`),
  });
}

export interface Contradiction {
  ticker: string;
  prediction_direction: "bullish" | "bearish";
  stance: "bull" | "bear";
  prediction_id: number;
  predicted_at: string;
}

/** #15 — open predictions whose direction opposes the ticker's house view. */
export function useContradictions() {
  return useQuery({
    queryKey: ["analytics/contradictions"],
    queryFn: () => apiGet<{ contradictions: Contradiction[] }>("/api/analytics/contradictions/"),
  });
}

export interface EvalReliabilityBucket {
  bin_low: number;
  bin_high: number;
  n: number;
  hits: number;
  observed_hit_rate: number | null;
  mean_confidence: number | null;
}

export interface EvalRunSummary {
  id: number;
  created_at: string;
  source: string;
  label: string;
  model: string;
  horizon: number | null;
  n: number;
  skipped: number;
  scored: number;
  hit_rate: number | null;
  brier: number | null;
  avg_confidence: number | null;
  calibration_error: number | null;
  calibration: EvalReliabilityBucket[];
}

/** Latest persisted offline eval run (M7). undefined when none has run yet (204). */
export function useLatestEvalRun() {
  return useQuery({
    queryKey: ["aieval/latest"],
    queryFn: () => apiGet<EvalRunSummary | null>("/api/aieval/runs/latest/"),
  });
}

export interface TrackRecord {
  ticker: string;
  closed_n: number;
  counts: { win: number; loss: number; scratch: number; invalidated: number };
  hit_rate: number | null;
  last: { direction: string; conviction: number; status: string } | null;
  slice: {
    direction: string;
    conviction: number;
    correct: number;
    n: number;
    hit_rate: number | null;
  } | null;
}

interface TrackRecordResponse {
  ticker: string;
  available: boolean;
  record: TrackRecord | null;
}

export function useTrackRecord(
  ticker: string,
  direction?: string,
  conviction?: number,
) {
  const params = new URLSearchParams();
  if (ticker) params.set("ticker", ticker);
  if (direction) params.set("direction", direction);
  if (conviction != null) params.set("conviction", String(conviction));
  return useQuery({
    queryKey: [
      "analytics/track-record",
      ticker,
      direction ?? null,
      conviction ?? null,
    ],
    queryFn: () =>
      apiGet<TrackRecordResponse>(
        `/api/analytics/track-record/?${params.toString()}`,
      ),
    enabled: Boolean(ticker),
  });
}

export interface TraderDecisionBucket {
  decision: string;
  n: number;
  correct: number;
  hit_rate: number;
}

export interface TraderConvictionBucket {
  conviction: number;
  n: number;
  correct: number;
  hit_rate: number;
}

export interface TraderCalibration {
  horizon_days: number;
  decision_outcomes: { status: string; buckets: TraderDecisionBucket[] };
  conviction_reliability: {
    status: string;
    buckets: TraderConvictionBucket[];
    verdict: string | null;
  };
}

/** The Mirror (M14 F4): grades the trader's OWN behavior. */
export function useTraderCalibration(horizon = 30) {
  return useQuery({
    queryKey: ["analytics/trader-calibration", horizon],
    queryFn: () =>
      apiGet<TraderCalibration>(
        `/api/analytics/trader-calibration/?horizon=${horizon}`,
      ),
  });
}
