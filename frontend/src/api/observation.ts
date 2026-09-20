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
  predicted_direction?: "bullish" | "bearish" | "neutral" | null;
  predicted_horizon_days?: number | null;
  predicted_confidence?: number | null;
  grounding?: string[];
};

/** One provider's opinion inside a consensus fan-out (mirrors observer/schemas.py ProviderTake). */
export type ProviderTake = {
  provider: string;
  model: string;
  bias: Bias;
  signal_bias: Record<string, Bias>;
};

/** Cross-provider agreement signal (mirrors observer/schemas.py ConsensusReport).
 * `per_ticker[ticker].takes` is keyed `"<provider>/<model>"`. */
export type ConsensusReport = {
  n_providers: number;
  bias_agreement: number | null;
  modal_bias: Bias | null;
  divergent: boolean;
  per_ticker: Record<string, { agreement: number | null; modal: Bias | null; takes: Record<string, Bias> }>;
  takes: ProviderTake[];
  note: string;
};

export type AiAttributionInfo = { provider: string; model: string };

/** Post-mortem narrative as stored in `PostMortem.report` / the `postmortem_report` Message. */
export type PostMortemReportContent = {
  summary: string;
  what_worked: string[];
  what_missed: string[];
  lessons: string[];
  would_repeat: boolean;
  ai?: AiAttributionInfo;
};

/** War Room synthesis as spread into the `warroom_verdict` Message content. */
export type WarRoomVerdictContent = {
  verdict?: string;
  confidence?: number;
  strongest_bull?: string;
  strongest_bear?: string;
  what_would_change_my_mind?: string;
  ai?: AiAttributionInfo;
};

/** Every `content.kind` the backend writes on an assistant/system Message. */
export type StructuredKind =
  | "structured_observation"
  | "consensus_report"
  | "postmortem_report"
  | "warroom_verdict"
  | "cached_observation"
  | "capability_warning"
  | "investigation";
export type StructuredReport = ObservationReport | ConsensusReport | PostMortemReportContent;

export function isConsensusReport(r: StructuredReport | undefined | null): r is ConsensusReport {
  return !!r && typeof r === "object" && "n_providers" in r;
}
export function isPostMortemReport(r: StructuredReport | undefined | null): r is PostMortemReportContent {
  return !!r && typeof r === "object" && "would_repeat" in r;
}
