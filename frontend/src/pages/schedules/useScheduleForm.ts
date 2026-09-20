import { useMemo, useState } from "react";
import type { CreateScheduleBody, ObserverFireMode } from "@/api/observer";
import { CRON_PRESETS, explainCron } from "@/lib/cronPreview";
import { BLANK_AI_FIELDS, type AiFieldsValue } from "./ScheduleAiFields";

/** Everything the create form holds, plus the body it submits. */
export function useScheduleForm() {
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState<number | null>(null);
  const [marketHoursOnly, setMarketHoursOnly] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [cronMode, setCronMode] = useState<"preset" | "advanced">("preset");
  const [presetIdx, setPresetIdx] = useState(1); // default to "Every 15 minutes"
  const [advancedCron, setAdvancedCron] = useState("*/15 * * * *");
  const [objective, setObjective] = useState("");
  const [fireMode, setFireMode] = useState<ObserverFireMode>("cron");
  const [closeOffset, setCloseOffset] = useState(5);
  const [ai, setAi] = useState<AiFieldsValue>(BLANK_AI_FIELDS);

  const cron = cronMode === "preset" ? CRON_PRESETS[presetIdx].cron : advancedCron;
  const cronEnglish = useMemo(() => explainCron(cron), [cron]);

  const payload = (): CreateScheduleBody => ({
    name,
    profile: profileId as number,
    enabled,
    market_hours_only: marketHoursOnly,
    objective_template: objective,
    ...ai,
    fire_mode: fireMode,
    ...(fireMode === "cron" ? { cron } : { close_offset_minutes: closeOffset }),
  });

  const reset = () => {
    setName("");
    setObjective("");
    setAi(BLANK_AI_FIELDS);
    setFireMode("cron");
    setCloseOffset(5);
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
    ai, setAi,
    cron, cronEnglish,
    payload, reset,
  };
}

export type ScheduleForm = ReturnType<typeof useScheduleForm>;
