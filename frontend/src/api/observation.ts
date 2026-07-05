// Structured ObservationReport domain types — the shape the AI returns for a
// "structured_observation". These live in the data layer (src/api) so api modules
// can reference them without importing UI, satisfying the dependency-cruiser
// `api-stays-below-ui` contract. The presentational <ObservationReportCard/>
// re-exports ObservationReport so UI code imports it from src/api.

export type Bias = "bullish" | "bearish" | "neutral" | "mixed";

export type ObservationReport = {
  headline: string;
  bias: Bias;
  summary: string;
  signals: Array<{
    ticker: string;
    bias: Bias;
    thesis: string;
    invalidation: string;
    confidence: number;
  }>;
  key_levels: Array<{
    label: string;
    price: number;
    kind: "support" | "resistance" | "pivot" | "target";
  }>;
  risks: string[];
  next_check_in: string;
};
