import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type Op =
  | ">" | ">=" | "<" | "<=" | "=="
  | "crosses_above" | "crosses_below";

export type Metric =
  | "price" | "pct_change" | "vix" | "position_pl" | "position_pl_pct";

export type Window = "1m" | "5m" | "15m" | "1h" | "1d";

export type Leaf = {
  metric: Metric;
  ticker?: string;
  op: Op;
  value: number;
  window?: Window;
};

export type Condition =
  | Leaf
  | { all: Condition[] }
  | { any: Condition[] }
  | { not: Condition };

export type EventTrigger = {
  id: number;
  name: string;
  profile: number;
  condition: Condition;
  cooldown_seconds: number;
  enabled: boolean;
  last_fired_at: string | null;
  firings_count: number;
  created_at: string;
  updated_at: string;
};

export type Firing = {
  id: number;
  trigger_id: number;
  trigger_name: string;
  fired_at: string;
  matched_values: Record<string, number | null>;
  snapshot_id: number | null;
  thread_id: number | null;
  cost_capped: boolean;
};

export type EvaluateResult = {
  matched: boolean;
  values: Record<string, number | null>;
  missing: string[];
};

export const fetchTriggers = () =>
  apiGet<EventTrigger[]>("/api/triggers/");

export const createTrigger = (
  body: Pick<EventTrigger, "name" | "profile" | "condition" | "cooldown_seconds" | "enabled">,
) => apiPost<EventTrigger>("/api/triggers/", body);

export const updateTrigger = (id: number, body: Partial<EventTrigger>) =>
  apiPatch<EventTrigger>(`/api/triggers/${id}/`, body);

export const deleteTrigger = (id: number) =>
  apiDelete(`/api/triggers/${id}/`);

export const fireTriggerNow = (id: number) =>
  apiPost<{ task_id: string }>(`/api/triggers/${id}/fire/`);

export const evaluateTrigger = (
  body: { condition: Condition; profile?: number } | { trigger_id: number },
) => apiPost<EvaluateResult>("/api/triggers/evaluate/", body);

export const fetchFirings = (triggerId: number, page = 1, size = 20) =>
  apiGet<{ results: Firing[]; count: number; page: number; size: number }>(
    `/api/triggers/${triggerId}/firings/?page=${page}&size=${size}`,
  );

export const fetchRecentFirings = (limit = 5) =>
  apiGet<Firing[]>(`/api/triggers/firings/recent/?limit=${limit}`);
