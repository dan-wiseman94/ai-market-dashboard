import { apiGet, apiPost, apiPatch } from "./client";

export type BriefingThesis = {
  id: number; ticker: string; direction: string; conviction: number;
  entry: number | null; target: number | null; invalidation: number | null;
  current: number | null; pct_to_target: number | null; pct_to_invalidation: number | null;
};
export type BriefingData = {
  theses: BriefingThesis[];
  events: { earnings: Array<Record<string, unknown>>; macro: Array<Record<string, unknown>> };
  triggers: Array<{ trigger_id: number; name: string; fired_at: string; summary: string }>;
  news: Array<{ headline: string; source: string; url: string; published_at: number; ticker: string }>;
  market: Record<string, unknown>;
  since: string;
};
export type Briefing = {
  id: number; created_at: string; status: string; scheduled_date: string | null;
  data: BriefingData; snapshot: number | null;
  synthesis_text: string; synthesis_status: string;
};
export type BriefingConfig = {
  /** Assemble + post one briefing per local day once `send_at_local` has passed. */
  enabled: boolean;
  /** Pay for one AI synthesis pass over each assembled briefing. Data sections render either way. */
  synthesis_enabled: boolean;
  send_at_local: string;
  profile: number | null;
  news_lookback_hours: number;
  events_within_days: number;
  updated_at: string;
};

/** DRF PageNumberPagination envelope for `GET /api/briefings/` (page_size 20). */
export type BriefingPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Briefing[];
};

export const fetchLatestBriefing = () => apiGet<Briefing | null>("/api/briefings/latest/");
export const fetchBriefings = (page = 1) =>
  apiGet<BriefingPage>(`/api/briefings/?page=${page}`);
export const runBriefingNow = () => apiPost<Briefing>("/api/briefings/run/", {});
export const fetchBriefingConfig = () => apiGet<BriefingConfig>("/api/briefings/config/");
export const patchBriefingConfig = (body: Partial<BriefingConfig>) =>
  apiPatch<BriefingConfig>("/api/briefings/config/", body);
