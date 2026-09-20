import type { ObserverFireMode } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { CRON_PRESETS } from "@/lib/cronPreview";
import ScheduleAiFields from "./ScheduleAiFields";
import type { ScheduleForm } from "./useScheduleForm";

function FireModeFields({
  fireMode, setFireMode, closeOffset, setCloseOffset,
}: {
  fireMode: ObserverFireMode;
  setFireMode: (v: ObserverFireMode) => void;
  closeOffset: number;
  setCloseOffset: (v: number) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-ink-500" htmlFor="sched-fire-mode">Fire mode</label>
      <select
        id="sched-fire-mode"
        value={fireMode}
        onChange={(e) => setFireMode(e.target.value as ObserverFireMode)}
        className="ledger-input w-full py-2"
      >
        <option value="cron">Cron schedule</option>
        <option value="relative_to_close">Relative to market close</option>
      </select>
      {fireMode === "relative_to_close" && (
        <label className="mt-2 block text-xs text-ink-500" htmlFor="sched-close-offset">
          Minutes before close
          <input
            id="sched-close-offset"
            type="number"
            min={0}
            value={closeOffset}
            onChange={(e) => setCloseOffset(parseInt(e.target.value, 10) || 0)}
            className="ledger-input mt-1 w-full py-2 tabular-nums"
          />
        </label>
      )}
    </div>
  );
}

function CronFields({ form }: { form: ScheduleForm }) {
  return (
    <div>
      <div className="mb-1 flex gap-2">
        <button
          type="button"
          onClick={() => form.setCronMode("preset")}
          className={form.cronMode === "preset" ? "ledger-cta" : "ledger-ghost"}
        >
          Preset
        </button>
        <button
          type="button"
          onClick={() => form.setCronMode("advanced")}
          className={form.cronMode === "advanced" ? "ledger-cta" : "ledger-ghost"}
        >
          Advanced
        </button>
      </div>
      {form.cronMode === "preset" ? (
        <select
          aria-label="Cron preset"
          value={form.presetIdx}
          onChange={(e) => form.setPresetIdx(parseInt(e.target.value, 10))}
          className="ledger-input w-full py-2"
        >
          {CRON_PRESETS.map((p, i) => <option key={p.cron} value={i}>{p.label}</option>)}
        </select>
      ) : (
        <input
          type="text"
          aria-label="Cron expression"
          value={form.advancedCron}
          onChange={(e) => form.setAdvancedCron(e.target.value)}
          className="ledger-input w-full py-2 font-mono"
        />
      )}
      <div className="mt-1 text-xs text-ink-500">{form.cron} — {form.cronEnglish}</div>
    </div>
  );
}

export default function CreateScheduleForm({
  profiles, isPending, onSubmit, form,
}: {
  profiles: TradingProfile[] | undefined;
  isPending: boolean;
  onSubmit: (e: React.FormEvent) => void;
  form: ScheduleForm;
}) {
  const profile = profiles?.find((p) => p.id === form.profileId);
  return (
    <form onSubmit={onSubmit} className="ledger-surface space-y-3 p-4">
      <div>
        <label className="mb-1 block text-xs text-ink-500" htmlFor="sched-name">Name</label>
        <input
          id="sched-name"
          type="text"
          value={form.name}
          onChange={(e) => form.setName(e.target.value)}
          required
          className="ledger-input w-full py-2"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs text-ink-500" htmlFor="sched-profile">Profile</label>
        <select
          id="sched-profile"
          value={form.profileId ?? ""}
          onChange={(e) => form.setProfileId(parseInt(e.target.value, 10))}
          className="ledger-input w-full py-2"
        >
          {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="flex gap-4 text-sm text-ink-200">
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => form.setEnabled(e.target.checked)}
          />
          enabled
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={form.marketHoursOnly}
            onChange={(e) => form.setMarketHoursOnly(e.target.checked)}
          />
          market hours only
        </label>
      </div>

      <FireModeFields
        fireMode={form.fireMode}
        setFireMode={form.setFireMode}
        closeOffset={form.closeOffset}
        setCloseOffset={form.setCloseOffset}
      />

      {form.fireMode === "cron" && <CronFields form={form} />}

      <div>
        <label className="mb-1 block text-xs text-ink-500" htmlFor="sched-objective">
          Objective template (sent with every fire)
        </label>
        <textarea
          id="sched-objective"
          rows={2}
          value={form.objective}
          onChange={(e) => form.setObjective(e.target.value)}
          className="ledger-input w-full py-2"
          placeholder="e.g. Flag any unusual options activity."
        />
      </div>

      <ScheduleAiFields
        value={form.ai}
        onChange={form.setAi}
        profile={profile}
        idPrefix="sched-new"
      />

      <button
        type="submit"
        disabled={isPending || !form.name || !form.profileId}
        className="ledger-cta disabled:opacity-40"
      >
        {isPending ? "Creating…" : "Create"}
      </button>
    </form>
  );
}
