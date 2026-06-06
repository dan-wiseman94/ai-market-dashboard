import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

export type ObserverMode = "full" | "diff";

export type ObserverFireMode = "cron" | "relative_to_close";

export interface ObserverSchedule {
  id: number;
  name: string;
  profile: number;
  enabled: boolean;
  market_hours_only: boolean;
  objective_template: string;
  override_provider: string;
  override_model: string;
  default_includes: string[];
  default_watchlist_tickers: string[];
  mode: ObserverMode;
  structured: boolean;
  use_batch: boolean;
  consensus: boolean;
  last_batch_id: string;
  last_fired_at: string | null;
  cron_display: string;
  created_at: string;
  updated_at: string;
  fire_mode: ObserverFireMode;
  close_offset_minutes: number;
}

export interface CreateScheduleBody {
  name: string;
  profile: number;
  cron?: string;
  enabled?: boolean;
  market_hours_only?: boolean;
  objective_template?: string;
  override_provider?: string;
  override_model?: string;
  default_includes?: string[];
  default_watchlist_tickers?: string[];
  mode?: ObserverMode;
  structured?: boolean;
  use_batch?: boolean;
  consensus?: boolean;
  fire_mode?: ObserverFireMode;
  close_offset_minutes?: number;
}

export const listSchedules = () => apiGet<ObserverSchedule[]>("/api/observer/schedules/");
export const createSchedule = (body: CreateScheduleBody) =>
  apiPost<ObserverSchedule>("/api/observer/schedules/", body);
export const patchSchedule = (id: number, body: Partial<CreateScheduleBody>) =>
  apiPatch<ObserverSchedule>(`/api/observer/schedules/${id}/`, body);
export const deleteSchedule = (id: number) =>
  apiDelete(`/api/observer/schedules/${id}/`);
export const runScheduleNow = (id: number) =>
  apiPost<void>(`/api/observer/schedules/${id}/run-now/`, {});

export interface NotificationDTO {
  id: number;
  kind: "trigger" | "observer_done" | "error" | "cost_limit" | "backup";
  title: string;
  body: string;
  link: string;
  meta: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export const listNotifications = (unread = false) =>
  apiGet<{ results: NotificationDTO[] } | NotificationDTO[]>(
    `/api/observer/notifications/?limit=50${unread ? "&unread=true" : ""}`,
  );
export const markNotificationRead = (id: number) =>
  apiPost<NotificationDTO>(`/api/observer/notifications/${id}/read/`, {});
export const markAllNotificationsRead = () =>
  apiPost<{ ok: true }>("/api/observer/notifications/mark-all-read/", {});

export interface MarketStatus {
  is_open: boolean;
  next_open: string | null;
  next_close: string | null;
}
export const getMarketStatus = () => apiGet<MarketStatus>("/api/observer/market-status/");
