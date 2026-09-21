/**
 * Form state for an observer schedule, shared by the create form and the
 * per-row edit expander so the two can never drift apart.
 *
 * Every writable serializer field is represented here. `cron` is derived
 * (preset index or the advanced string) rather than stored twice.
 */

import { CRON_PRESETS } from "@/lib/cronPreview";
import { DEFAULT_PICK, type ProviderModelPick } from "@/lib/modelDefaults";
import type {
  CreateScheduleBody, ObserverFireMode, ObserverMode, ObserverSchedule,
} from "@/api/observer";

export interface ScheduleFormValues {
  name: string;
  enabled: boolean;
  marketHoursOnly: boolean;
  fireMode: ObserverFireMode;
  closeOffset: number;
  cronMode: "preset" | "advanced";
  presetIdx: number;
  advancedCron: string;
  objective: string;
  mode: ObserverMode;
  structured: boolean;
  useBatch: boolean;
  consensus: boolean;
  investigate: boolean;
  /** False = inherit the profile's provider/model (sends empty overrides). */
  overrideModel: boolean;
  override: ProviderModelPick;
  watchlistTickers: string[];
}

const DEFAULT_PRESET_IDX = 1; // "Every 15 minutes"

/** Blank slate for the create form. `investigate` matches the model default (on). */
export function emptyScheduleValues(): ScheduleFormValues {
  return {
    name: "",
    enabled: true,
    marketHoursOnly: true,
    fireMode: "cron",
    closeOffset: 5,
    cronMode: "preset",
    presetIdx: DEFAULT_PRESET_IDX,
    advancedCron: CRON_PRESETS[DEFAULT_PRESET_IDX].cron,
    objective: "",
    mode: "full",
    structured: false,
    useBatch: false,
    consensus: false,
    investigate: true,
    overrideModel: false,
    override: { ...DEFAULT_PICK },
    watchlistTickers: [],
  };
}

/** Seed the edit form from a saved schedule. Every field round-trips. */
export function scheduleToValues(s: ObserverSchedule): ScheduleFormValues {
  const base = emptyScheduleValues();
  const cron = s.cron_display || "";
  const presetIdx = CRON_PRESETS.findIndex((p) => p.cron === cron);
  const hasOverride = Boolean(s.override_provider || s.override_model);
  return {
    ...base,
    name: s.name,
    enabled: s.enabled,
    marketHoursOnly: s.market_hours_only,
    fireMode: s.fire_mode ?? "cron",
    closeOffset: s.close_offset_minutes ?? base.closeOffset,
    cronMode: presetIdx >= 0 ? "preset" : "advanced",
    presetIdx: presetIdx >= 0 ? presetIdx : base.presetIdx,
    advancedCron: cron || base.advancedCron,
    objective: s.objective_template ?? "",
    mode: s.mode ?? "full",
    structured: Boolean(s.structured),
    useBatch: Boolean(s.use_batch),
    consensus: Boolean(s.consensus),
    investigate: Boolean(s.investigate),
    overrideModel: hasOverride,
    override: hasOverride
      ? { provider: s.override_provider, model: s.override_model }
      : { ...DEFAULT_PICK },
    watchlistTickers: s.default_watchlist_tickers ?? [],
  };
}

/** The cron expression the form currently resolves to. */
export function cronOf(v: ScheduleFormValues): string {
  return v.cronMode === "preset" ? CRON_PRESETS[v.presetIdx].cron : v.advancedCron;
}

/**
 * The request body for create *and* update — the same shape both ways, so an
 * edit can never silently omit a field the create form set.
 */
export function buildSchedulePayload(
  v: ScheduleFormValues,
  profileId: number,
): CreateScheduleBody {
  return {
    name: v.name,
    profile: profileId,
    enabled: v.enabled,
    market_hours_only: v.marketHoursOnly,
    objective_template: v.objective,
    override_provider: v.overrideModel ? v.override.provider : "",
    override_model: v.overrideModel ? v.override.model : "",
    default_watchlist_tickers: v.watchlistTickers,
    mode: v.mode,
    structured: v.structured,
    use_batch: v.useBatch,
    consensus: v.consensus,
    investigate: v.investigate,
    fire_mode: v.fireMode,
    ...(v.fireMode === "cron"
      ? { cron: cronOf(v) }
      : { close_offset_minutes: v.closeOffset }),
  };
}
