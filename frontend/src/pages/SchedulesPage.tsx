import { useMemo, useState } from "react";
import {
  useSchedules, useToggleSchedule, useDeleteSchedule,
  useRunSchedule, useCreateSchedule,
} from "@/hooks/useSchedules";
import { useProfiles } from "@/hooks/useProfiles";
import { CRON_PRESETS, explainCron } from "@/lib/cronPreview";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import type { ObserverFireMode, ObserverMode } from "@/api/observer";

export default function SchedulesPage() {
  const { data: schedules, isLoading } = useSchedules();
  const { data: profiles } = useProfiles();
  const toggle = useToggleSchedule();
  const del = useDeleteSchedule();
  const run = useRunSchedule();
  const create = useCreateSchedule();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState<number | null>(null);
  const [marketHoursOnly, setMarketHoursOnly] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [cronMode, setCronMode] = useState<"preset" | "advanced">("preset");
  const [presetIdx, setPresetIdx] = useState(1); // default to "Every 15 minutes"
  const [advancedCron, setAdvancedCron] = useState("*/15 * * * *");
  const [objective, setObjective] = useState("");
  const [mode, setMode] = useState<ObserverMode>("full");
  const [structured, setStructured] = useState(false);
  const [useBatch, setUseBatch] = useState(false);
  const [fireMode, setFireMode] = useState<ObserverFireMode>("cron");
  const [closeOffset, setCloseOffset] = useState(5);

  const cron = cronMode === "preset" ? CRON_PRESETS[presetIdx].cron : advancedCron;
  const cronEnglish = useMemo(() => explainCron(cron), [cron]);

  // Default to the first profile once loaded. Render-phase guarded update
  // (React's "adjust state when data changes") rather than an effect, which
  // avoids react-hooks/set-state-in-effect cascading renders.
  if (profileId === null && profiles && profiles.length > 0) {
    setProfileId(profiles[0].id);
  }

  const profileName = (id: number) =>
    profiles?.find((p) => p.id === id)?.name ?? `#${id}`;

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!profileId) return;
    await create.mutateAsync({
      name, profile: profileId, enabled, market_hours_only: marketHoursOnly,
      objective_template: objective,
      mode, structured, use_batch: useBatch,
      fire_mode: fireMode,
      ...(fireMode === "cron" ? { cron } : { close_offset_minutes: closeOffset }),
    });
    setName(""); setObjective("");
    setMode("full"); setStructured(false); setUseBatch(false);
    setFireMode("cron"); setCloseOffset(5);
    setShowForm(false);
  }

  if (isLoading) {
    return (
      <main className="p-6 max-w-3xl mx-auto space-y-4">
        <h1 className="text-2xl font-semibold">Observer schedules</h1>
        <SkeletonRows rows={3} />
      </main>
    );
  }

  const rows = Array.isArray(schedules) ? schedules : [];

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Observer schedules</h1>

      {rows.length === 0 && (
        <EmptyState
          title="No schedules yet"
          body="Create one to have the observer capture + analyze snapshots on a cron."
        />
      )}

      <ul className="space-y-2">
        {rows.map((s) => (
          <li key={s.id} data-testid={`schedule-row-${s.id}`} className="p-4 rounded border border-rule bg-ink-900 space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold">{s.name}</div>
                <div className="text-xs text-ink-500">
                  {profileName(s.profile)} — {s.cron_display} ({explainCron(s.cron_display)})
                </div>
                {s.last_fired_at && (
                  <div className="text-xs text-ink-500">
                    Last fired {new Date(s.last_fired_at).toLocaleString()}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    onChange={(e) => toggle.mutate({ id: s.id, enabled: e.target.checked })}
                  />
                  enabled
                </label>
                <button type="button" onClick={() => run.mutate(s.id)}
                        className="px-2 py-1 text-xs rounded bg-gain-500 hover:bg-gain-400">Run now</button>
                <button type="button" onClick={() => del.mutate(s.id)}
                        aria-label={`delete ${s.name}`}
                        className="px-2 py-1 text-xs rounded bg-loss-500 hover:bg-loss-400">Delete</button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => setShowForm((v) => !v)}
        className="px-3 py-1 rounded bg-ink-700 hover:bg-ink-600"
      >{showForm ? "Cancel" : "+ New schedule"}</button>

      {showForm && (
        <form onSubmit={onCreate} className="p-4 rounded border border-rule bg-ink-900 space-y-3">
          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="sched-name">Name</label>
            <input
              id="sched-name"
              type="text" value={name} onChange={(e) => setName(e.target.value)} required
              className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule ledger-input"
            />
          </div>

          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="sched-profile">Profile</label>
            <select
              id="sched-profile"
              value={profileId ?? ""} onChange={(e) => setProfileId(parseInt(e.target.value, 10))}
              className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
            >
              {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              enabled
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={marketHoursOnly} onChange={(e) => setMarketHoursOnly(e.target.checked)} />
              market hours only
            </label>
          </div>

          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="sched-fire-mode">Fire mode</label>
            <select
              id="sched-fire-mode"
              value={fireMode}
              onChange={(e) => setFireMode(e.target.value as ObserverFireMode)}
              className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
            >
              <option value="cron">Cron schedule</option>
              <option value="relative_to_close">Relative to market close</option>
            </select>
            {fireMode === "relative_to_close" && (
              <label className="block text-xs text-ink-500 mt-2" htmlFor="sched-close-offset">
                Minutes before close
                <input
                  id="sched-close-offset"
                  type="number"
                  min={0}
                  value={closeOffset}
                  onChange={(e) => setCloseOffset(parseInt(e.target.value, 10) || 0)}
                  className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule mt-1"
                />
              </label>
            )}
          </div>

          {fireMode === "cron" && (
          <div>
            <div className="flex gap-2 mb-1">
              <button type="button" onClick={() => setCronMode("preset")}
                      className={`px-2 py-1 text-xs rounded ${cronMode === "preset" ? "bg-ink-700" : "bg-ink-800"}`}>Preset</button>
              <button type="button" onClick={() => setCronMode("advanced")}
                      className={`px-2 py-1 text-xs rounded ${cronMode === "advanced" ? "bg-ink-700" : "bg-ink-800"}`}>Advanced</button>
            </div>
            {cronMode === "preset" ? (
              <select value={presetIdx} onChange={(e) => setPresetIdx(parseInt(e.target.value, 10))}
                      className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule">
                {CRON_PRESETS.map((p, i) => <option key={p.cron} value={i}>{p.label}</option>)}
              </select>
            ) : (
              <input type="text" value={advancedCron} onChange={(e) => setAdvancedCron(e.target.value)}
                     className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule font-mono" />
            )}
            <div className="text-xs text-ink-500 mt-1">{cron} — {cronEnglish}</div>
          </div>
          )}

          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="sched-objective">Objective template (sent with every fire)</label>
            <textarea
              id="sched-objective"
              rows={2} value={objective} onChange={(e) => setObjective(e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
              placeholder="e.g. Flag any unusual options activity."
            />
          </div>

          <fieldset className="grid grid-cols-2 gap-3 text-sm border border-rule rounded p-3">
            <legend className="px-1 text-xs text-ink-500 uppercase tracking-wide">AI mode</legend>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-500">Payload shape</span>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as ObserverMode)}
                className="px-2 py-1 rounded bg-ink-850 border border-rule"
              >
                <option value="full">Full payload</option>
                <option value="diff">Diff vs previous capture</option>
              </select>
            </label>
            <label className="flex items-center gap-2 mt-6">
              <input
                type="checkbox" checked={structured}
                onChange={(e) => setStructured(e.target.checked)}
              />
              <span>Structured (typed observation card)</span>
            </label>
            <label className="flex items-center gap-2 col-span-2">
              <input
                type="checkbox" checked={useBatch}
                onChange={(e) => setUseBatch(e.target.checked)}
              />
              <span>Messages Batch per watchlist ticker (50% cheaper, async)</span>
            </label>
          </fieldset>

          <button type="submit" disabled={create.isPending || !name || !profileId}
                  className="px-3 py-1.5 rounded bg-gain-500 hover:bg-gain-400 disabled:opacity-40">
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </form>
      )}
    </main>
  );
}
