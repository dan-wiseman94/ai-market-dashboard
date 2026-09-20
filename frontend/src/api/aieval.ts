import { apiGet, apiPost } from "./client";

export type EvalReliabilityBucket = {
  bin_low: number;
  bin_high: number;
  n: number;
  hits: number;
  observed_hit_rate: number | null;
  mean_confidence: number | null;
};

/** One persisted offline eval run. `provider` names the vendor: a local model id
 * doesn't, so the model alone can't attribute a run. */
export type EvalRun = {
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
};

export type EvalRunRequest = {
  provider: string;
  model: string;
  horizon: number;
  limit: number;
  label: string;
};

export type EvalRunQueued = EvalRunRequest & { queued: true };

export const fetchEvalRuns = () => apiGet<EvalRun[]>("/api/aieval/runs/");
export const fetchLatestEvalRun = () => apiGet<EvalRun | null>("/api/aieval/runs/latest/");
export const triggerEvalRun = (body: EvalRunRequest) =>
  apiPost<EvalRunQueued>("/api/aieval/runs/", body);
