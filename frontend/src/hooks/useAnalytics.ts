import { useQuery } from "@tanstack/react-query";

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

async function fetchJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

function startISO(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

export function useLeaderboard(days = 30, forwardHours = 24) {
  return useQuery({
    queryKey: ["analytics/leaderboard", days, forwardHours],
    queryFn: () =>
      fetchJSON<{ rows: LeaderboardRow[] }>(
        `/api/analytics/leaderboard/?forward_hours=${forwardHours}` +
          `&start=${startISO(days)}`,
      ),
  });
}

export function useCostPerInsight(days = 30) {
  return useQuery({
    queryKey: ["analytics/cpi", days],
    queryFn: () =>
      fetchJSON<CostPerInsight>(
        `/api/analytics/cost-per-insight/?start=${startISO(days)}`,
      ),
  });
}

export function useTriggerHeatmap(days = 30) {
  return useQuery({
    queryKey: ["analytics/trigger-heatmap", days],
    queryFn: () =>
      fetchJSON<{ cells: HeatmapCell[] }>(
        `/api/analytics/trigger-heatmap/?start=${startISO(days)}`,
      ),
  });
}

export function useObserverTimeline(days = 30) {
  return useQuery({
    queryKey: ["analytics/observer-timeline", days],
    queryFn: () =>
      fetchJSON<{ days: TimelineDay[] }>(
        `/api/analytics/observer-timeline/?start=${startISO(days)}`,
      ),
  });
}

export function useUnusualOptions(ticker: string) {
  return useQuery({
    queryKey: ["analytics/unusual-options", ticker],
    queryFn: () =>
      fetchJSON<{ rows: UnusualRow[] }>(
        `/api/analytics/unusual-options/?ticker=${encodeURIComponent(ticker)}`,
      ),
    enabled: !!ticker,
  });
}
