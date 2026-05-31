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
