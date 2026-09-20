import { DEFAULT_PICK } from "@/lib/modelDefaults";
import { SECTION_KINDS } from "@/lib/snapshotSections";

/** Every user-toggleable section kind (`vix` is always-on, excluded — see snapshotSections.ts). */
export const SECTION_OPTIONS = SECTION_KINDS;

export type Draft = {
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  enable_tools: boolean;
  enable_thinking: boolean;
  thinking_budget: number;
  enable_memory: boolean;
  enable_coach: boolean;
};

// Mirrors TradingProfile.DEFAULT_INCLUDES (backend/apps/profiles/models.py) — the
// backend only seeds an EMPTY default_includes, so a UI-created profile that
// disagrees with this list silently ships without the rich defaults.
export const BLANK_DRAFT: Draft = {
  name: "", style: "",
  default_includes: ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"],
  default_provider: DEFAULT_PICK.provider, default_model: DEFAULT_PICK.model,
  // Mirrors the TradingProfile field defaults (backend/apps/profiles/models.py).
  enable_tools: false,
  enable_thinking: false,
  thinking_budget: 8000,
  enable_memory: false,
  enable_coach: true,
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
