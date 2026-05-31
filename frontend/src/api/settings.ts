import { apiGet, apiPatch } from "./client";

export interface SystemSettings {
  retention_ohlc_days: number;
  retention_chain_days: number;
  retention_notification_days: number;
  retention_error_days: number;
  ai_failover_enabled: boolean;
  ai_failover_provider: string;
  observer_response_cache_enabled: boolean;
  observer_response_cache_ttl_seconds: number;
  aieval_scheduled_enabled: boolean;
  aieval_scheduled_model: string;
  aieval_scheduled_horizon: number;
  aieval_scheduled_limit: number;
}

export const fetchSystemSettings = () => apiGet<SystemSettings>("/api/settings/");
export const updateSystemSettings = (patch: Partial<SystemSettings>) =>
  apiPatch<SystemSettings>("/api/settings/", patch);
