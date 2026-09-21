/** Stance presentation for the coverage house view — shared by the index and
 * the per-ticker detail page so the two can't drift on wording or colour. */
import type { Stance } from "@/hooks/useCoverage";

export const STANCE_LABEL: Record<Stance, string> = {
  bull: "Bullish",
  bear: "Bearish",
  neutral: "Neutral",
};

export const STANCE_TONE: Record<Stance, string> = {
  bull: "text-copper-300",
  bear: "text-ink-200",
  neutral: "text-ink-400",
};

/** Conviction rendered as a fraction of the 1–5 scale the model writes on. */
export const CONVICTION_MAX = 5;

export function convictionLabel(conviction: number): string {
  return `${conviction}/${CONVICTION_MAX}`;
}
