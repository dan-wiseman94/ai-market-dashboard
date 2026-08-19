import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/api/client";
import type { DashboardBook } from "@/components/BookTile";
import type { DashboardDesk } from "@/components/DeskTile";
import type { DashboardRegime } from "@/components/RegimeTile";

// ---------------------------------------------------------------------------
// Types — match views.py DashboardView payload exactly
// ---------------------------------------------------------------------------

export interface DashboardThesis {
  id: number;
  ticker: string;
  direction: string;
  conviction: number;
  entry: number | null;
  target: number | null;
  invalidation: number | null;
  current: number | null;
  pct_to_target: number | null;
  pct_to_invalidation: number | null;
}

export interface DashboardEvent {
  kind: string;
  ticker: string | null;
  title: string;
  event_time: string;
  days_until: number;
  when_hint: string;
  impact: string;
  detail: Record<string, unknown>;
}

export interface DashboardEvents {
  earnings: DashboardEvent[];
  macro: DashboardEvent[];
}

export interface DashboardObserver {
  enabled_schedules: number;
  runs_today: number;
}

export interface DashboardFiring {
  id: number;
  trigger_id: number;
  trigger_name: string | null;
  fired_at: string;
  cost_capped: boolean;
}

export interface DashboardTriggers {
  armed_count: number;
  latest_firings: DashboardFiring[];
}

export interface DashboardBriefing {
  id: number;
  status: string;
  created_at: string;
  scheduled_date: string | null;
}

export interface DashboardData {
  theses: DashboardThesis[];
  events: DashboardEvents;
  observer: DashboardObserver;
  triggers: DashboardTriggers;
  briefing: DashboardBriefing | null;
  regime: DashboardRegime;
  book: DashboardBook;
  desk: DashboardDesk;
}

export type { DashboardBook, DashboardDesk, DashboardRegime };

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiGet<DashboardData>("/api/dashboard/"),
  });
}
