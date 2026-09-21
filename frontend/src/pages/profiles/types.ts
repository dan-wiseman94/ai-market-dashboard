import type { Effort } from "@/api/profiles";
import { DEFAULT_PICK } from "@/lib/modelDefaults";
import { SECTION_KINDS } from "@/lib/snapshotSections";

/** Every user-toggleable section kind (`vix` is always-on, excluded — see snapshotSections.ts). */
export const SECTION_OPTIONS = SECTION_KINDS;

/** The effort ladder, cheapest first — mirrors TradingProfile.EFFORT_CHOICES. */
export const EFFORT_OPTIONS: readonly { value: Effort; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "Extra high" },
  { value: "max", label: "Max" },
];

export type Draft = {
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  enable_tools: boolean;
  enable_thinking: boolean;
  thinking_budget: number;
  effort: Effort;
  enable_memory: boolean;
  enable_coach: boolean;
  active: boolean;
};

// Mirrors TradingProfile.DEFAULT_INCLUDES (backend/apps/profiles/models.py) — the
// backend only seeds an EMPTY default_includes, so a UI-created profile that
// disagrees with this list silently ships without the rich defaults.
// The capability values mirror the TradingProfile field defaults in the same
// file, which are ON: a form that shipped them off would quietly create
// profiles weaker than the ones the backend makes.
export const BLANK_DRAFT: Draft = {
  name: "", style: "",
  default_includes: ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"],
  default_provider: DEFAULT_PICK.provider, default_model: DEFAULT_PICK.model,
  enable_tools: true,
  enable_thinking: true,
  thinking_budget: 8000,
  effort: "high",
  enable_memory: true,
  enable_coach: true,
  active: true,
};

export type PresetDraft = {
  name: string;
  description: string;
  objective_template: string;
  structured: boolean;
  active: boolean;
};

export const BLANK_PRESET_DRAFT: PresetDraft = {
  name: "",
  description: "",
  objective_template: "",
  structured: false,
  active: true,
};

/** Toggle a section name in/out of an includes list (add if absent, remove if present). */
export function toggleInArray(list: string[], value: string): string[] {
  return list.includes(value)
    ? list.filter((s) => s !== value)
    : [...list, value];
}
