import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/api/client";

export interface AIView {
  ticker: string;
  has_view: boolean;
  direction?: string;
  confidence?: number;
  horizon_days?: number;
  predicted_at?: string;
  rationale?: string;
  provider?: string;
  model?: string;
  agreement?: "agree" | "diverge" | "partial" | null;
}

/** The AI's current live call on a ticker (M13), reconciled against a thesis direction. */
export function useAIView(ticker: string, against?: string) {
  return useQuery({
    queryKey: ["predictions/ai-view", ticker, against ?? null],
    queryFn: () => {
      const a = against ? `&against=${encodeURIComponent(against)}` : "";
      return apiGet<AIView>(`/api/predictions/ai-view/?ticker=${encodeURIComponent(ticker)}${a}`);
    },
    enabled: !!ticker,
  });
}

export interface Divergence {
  thesis_id: number;
  ticker: string;
  title: string;
  thesis_direction: string;
  conviction: number;
  ai_direction: string;
  ai_confidence: number;
  ai_horizon_days: number;
  agreement: "diverge" | "partial";
}

export interface DivergencesResponse {
  count: number;
  rows: Divergence[];
}

/** Open theses that conflict with the AI's current call (M13 F7 dashboard rollup). */
export function useDivergences() {
  return useQuery({
    queryKey: ["predictions/divergences"],
    queryFn: () => apiGet<DivergencesResponse>("/api/predictions/divergences/"),
  });
}
