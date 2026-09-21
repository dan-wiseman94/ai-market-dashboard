import { apiGet, apiPatch } from "./client";

export interface SystemSettings {
  retention_ohlc_days: number;
  retention_chain_days: number;
  retention_notification_days: number;
  retention_error_days: number;
  retention_regime_days: number;
  retention_desk_days: number;
  retention_book_days: number;
  ai_failover_enabled: boolean;
  ai_failover_provider: string;
  observer_response_cache_enabled: boolean;
  observer_response_cache_ttl_seconds: number;
  aieval_scheduled_enabled: boolean;
  aieval_scheduled_model: string;
  aieval_scheduled_horizon: number;
  aieval_scheduled_limit: number;
  tradingview_tools_enabled: boolean;
  ai_calibration_routing_enabled: boolean;
  calibration_drift_sentinel_enabled: boolean;
  anomaly_sweep_enabled: boolean;
  returns_adjust_dividends: boolean;
  ai_investigation_max_iterations: number;
  ai_autonomous_daily_cap_usd: number;
  ai_calibration_routing_min_scored: number;
  ai_calibration_routing_max_age_days: number;
  restore_from_ui_enabled: boolean;
  ai_chat_max_tool_iterations: number;
}

/**
 * PATCH body. `null` is meaningful, not missing: it clears the stored override so the
 * field inherits the backend default again ("Reset to default"). Partial<SystemSettings>
 * is assignable to this, so callers that only ever send values need no change.
 */
export type SystemSettingsPatch = { [K in keyof SystemSettings]?: SystemSettings[K] | null };

export const fetchSystemSettings = () => apiGet<SystemSettings>("/api/settings/");
export const updateSystemSettings = (patch: SystemSettingsPatch) =>
  apiPatch<SystemSettings>("/api/settings/", patch);
