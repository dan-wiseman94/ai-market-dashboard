import cronstrue from "cronstrue";

export interface CronPreset {
  label: string;
  cron: string;
}

// Cron expressions evaluate in OBSERVER_BEAT_TIMEZONE (default "UTC", set to
// "America/New_York" for the *ET presets below to be correct year-round).
export const CRON_PRESETS: CronPreset[] = [
  { label: "Every 5 minutes", cron: "*/5 * * * *" },
  { label: "Every 15 minutes", cron: "*/15 * * * *" },
  { label: "Hourly", cron: "0 * * * *" },
  { label: "Daily 9:35 ET (requires OBSERVER_BEAT_TIMEZONE=America/New_York)", cron: "35 9 * * 1-5" },
  { label: "Daily 16:00 ET (requires OBSERVER_BEAT_TIMEZONE=America/New_York)", cron: "0 16 * * 1-5" },
];

export function explainCron(cron: string): string {
  try {
    return cronstrue.toString(cron);
  } catch (e) {
    return `Invalid cron: ${(e as Error).message}`;
  }
}
