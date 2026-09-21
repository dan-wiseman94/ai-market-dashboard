import { useMemo, useState } from "react";
import type {
  CreateScheduleBody, ObserverFireMode, ObserverSchedule,
} from "@/api/observer";
import { CRON_PRESETS, explainCron } from "@/lib/cronPreview";
import { BLANK_AI_FIELDS, aiFieldsFrom, type AiFieldsValue } from "./ScheduleAiFields";

const DEFAULT_PRESET_IDX = 1; // "Every 15 minutes"

/** The cadence, split into the two ways the form can express it. */
function cronSeed(cron: string) {
  const presetIdx = CRON_PRESETS.findIndex((p) => p.cron === cron);
  return {
    cronMode: (cron && presetIdx < 0 ? "advanced" : "preset") as "preset" | "advanced",
    presetIdx: presetIdx >= 0 ? presetIdx : DEFAULT_PRESET_IDX,
    advancedCron: cron || CRON_PRESETS[DEFAULT_PRESET_IDX].cron,
  };
}

/** A new schedule's starting point. */
const BLANK = {
  name: "",
  profileId: null as number | null,
  enabled: true,
  marketHoursOnly: true,
  objective: "",
  fireMode: "cron" as ObserverFireMode,
  closeOffset: 5,
  tickers: [] as string[],
  ai: BLANK_AI_FIELDS,
  ...cronSeed(""),
};

/** Seed the form from a saved schedule. Every writable field round-trips. */
function seedFrom(seed: ObserverSchedule | undefined) {
  if (!seed) return BLANK;
  return {
    name: seed.name,
    profileId: seed.profile as number | null,
    enabled: seed.enabled,
    marketHoursOnly: seed.market_hours_only,
    objective: seed.objective_template ?? "",
    fireMode: seed.fire_mode ?? BLANK.fireMode,
    closeOffset: seed.close_offset_minutes ?? BLANK.closeOffset,
    tickers: seed.default_watchlist_tickers ?? [],
    ai: aiFieldsFrom(seed),
    ...cronSeed(seed.cron_display ?? ""),
  };
}

/**
 * Everything a schedule form holds, plus the body it submits.
 *
 * One hook for both paths: the create form mounts it blank, the per-row editor
 * mounts it seeded from the saved schedule, so an edit can never omit a field
 * the create form could set.
 */
export function useScheduleForm(seed?: ObserverSchedule) {
  const init = seedFrom(seed);
  const [name, setName] = useState(init.name);
  const [profileId, setProfileId] = useState<number | null>(init.profileId);
  const [marketHoursOnly, setMarketHoursOnly] = useState(init.marketHoursOnly);
  const [enabled, setEnabled] = useState(init.enabled);
  const [cronMode, setCronMode] = useState<"preset" | "advanced">(init.cronMode);
  const [presetIdx, setPresetIdx] = useState(init.presetIdx);
  const [advancedCron, setAdvancedCron] = useState(init.advancedCron);
  const [objective, setObjective] = useState(init.objective);
  const [fireMode, setFireMode] = useState<ObserverFireMode>(init.fireMode);
  const [closeOffset, setCloseOffset] = useState(init.closeOffset);
  const [tickers, setTickers] = useState<string[]>(init.tickers);
  const [ai, setAi] = useState<AiFieldsValue>(init.ai);

  const cron = cronMode === "preset" ? CRON_PRESETS[presetIdx].cron : advancedCron;
  const cronEnglish = useMemo(() => explainCron(cron), [cron]);

  const payload = (): CreateScheduleBody => ({
    name,
    profile: profileId as number,
    enabled,
    market_hours_only: marketHoursOnly,
    objective_template: objective,
    default_watchlist_tickers: tickers,
    ...ai,
    fire_mode: fireMode,
    ...(fireMode === "cron" ? { cron } : { close_offset_minutes: closeOffset }),
  });

  const reset = () => {
    setName(BLANK.name);
    setObjective(BLANK.objective);
    setTickers(BLANK.tickers);
    setAi(BLANK.ai);
    setFireMode(BLANK.fireMode);
    setCloseOffset(BLANK.closeOffset);
  };

  return {
    name, setName,
    profileId, setProfileId,
    enabled, setEnabled,
    marketHoursOnly, setMarketHoursOnly,
    cronMode, setCronMode,
    presetIdx, setPresetIdx,
    advancedCron, setAdvancedCron,
    objective, setObjective,
    fireMode, setFireMode,
    closeOffset, setCloseOffset,
    tickers, setTickers,
    ai, setAi,
    cron, cronEnglish,
    payload, reset,
  };
}

export type ScheduleForm = ReturnType<typeof useScheduleForm>;
