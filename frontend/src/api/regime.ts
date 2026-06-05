import { apiGet, apiPost } from "@/api/client";

export type RegimeComposite = "Risk-On" | "Neutral-Transitional" | "Risk-Off" | "Stress";

export interface RegimeReading {
  id: number;
  created_at: string;
  composite: RegimeComposite;
  axes: Record<string, string>;
  drivers: string[];
  narrative: string;
  changed_axes: string[];
}

export const fetchCurrentRegime = () => apiGet<RegimeReading | null>("/api/regime/current/");
export const fetchRegimeHistory = () => apiGet<RegimeReading[]>("/api/regime/");
/** @public — typed client for POST /api/regime/refresh/; awaits a UI "refresh" affordance. */
export const refreshRegime = () => apiPost<RegimeReading>("/api/regime/refresh/");
