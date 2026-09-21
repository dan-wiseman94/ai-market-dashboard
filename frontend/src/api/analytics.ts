import { apiGet, apiPost } from "./client";

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
  provider: string;
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

export type EvalProvider = "claude" | "openai" | "local";

/**
 * Body of POST /api/aieval/runs/. Every field is optional — the backend fills
 * omissions from `runtime_config()`. `horizon: null` means "every horizon".
 */
export interface EvalRunRequest {
  provider?: EvalProvider;
  model?: string;
  horizon?: number | null;
  limit?: number;
  label?: string;
  system?: string;
}

/** 202 body: the queued Celery task plus the fully resolved parameters. */
export interface EvalRunQueued {
  task_id: string;
  status: string;
  provider: string;
  model: string;
  horizon: number | null;
  limit: number;
  label: string;
  system: string | null;
}

/** Recent persisted eval runs, newest first (the backend caps the list at 50). */
export const fetchEvalRuns = () => apiGet<EvalRunSummary[]>("/api/aieval/runs/");

/** Latest persisted eval run. `null` when none has run yet (the endpoint 204s). */
export const fetchLatestEvalRun = () => apiGet<EvalRunSummary | null>("/api/aieval/runs/latest/");

/**
 * Queue a calibration eval. SPENDS REAL MONEY — one billed model call per
 * replayed snapshot — and is refused with 409 under MOCK_EXTERNAL or 429 when
 * the provider's monthly cost cap is already hit. Fire-and-forget: the 202
 * carries a task id, never a result.
 */
export const queueEvalRun = (body: EvalRunRequest) =>
  apiPost<EvalRunQueued>("/api/aieval/runs/", body);
