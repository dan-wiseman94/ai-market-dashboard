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
