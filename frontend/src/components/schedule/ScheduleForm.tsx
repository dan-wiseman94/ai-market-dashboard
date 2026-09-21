import ProviderModelPicker from "@/components/ProviderModelPicker";
import TickerChipsInput from "@/components/TickerChipsInput";
import InvestigateToggle from "@/components/schedule/InvestigateToggle";
import { CRON_PRESETS, explainCron } from "@/lib/cronPreview";
import type { ObserverFireMode, ObserverMode } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { cronOf, type ScheduleFormValues } from "./scheduleFormValues";

/** Patch-style update so callers never rebuild the whole value object. */
export type ScheduleFormChange = (patch: Partial<ScheduleFormValues>) => void;

interface FieldGroupProps {
  idPrefix: string;
  values: ScheduleFormValues;
  onChange: ScheduleFormChange;
}

function FireModeFields({ idPrefix, values, onChange }: FieldGroupProps) {
  return (
    <div>
      <label className="block text-xs text-ink-500 mb-1" htmlFor={`${idPrefix}-fire-mode`}>
        Fire mode
      </label>
      <select
        id={`${idPrefix}-fire-mode`}
        value={values.fireMode}
        onChange={(e) => onChange({ fireMode: e.target.value as ObserverFireMode })}
        className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
      >
        <option value="cron">Cron schedule</option>
        <option value="relative_to_close">Relative to market close</option>
      </select>
      {values.fireMode === "relative_to_close" && (
        <label className="block text-xs text-ink-500 mt-2" htmlFor={`${idPrefix}-close-offset`}>
          Minutes before close
          <input
            id={`${idPrefix}-close-offset`}
            type="number"
            min={0}
            value={values.closeOffset}
            onChange={(e) => onChange({ closeOffset: parseInt(e.target.value, 10) || 0 })}
            className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule mt-1"
          />
        </label>
      )}
    </div>
  );
}

function CronFields({ idPrefix, values, onChange }: FieldGroupProps) {
  const cron = cronOf(values);
  return (
    <div>
      <div className="flex gap-2 mb-1">
        <button type="button" onClick={() => onChange({ cronMode: "preset" })}
                className={`px-2 py-1 text-xs rounded ${values.cronMode === "preset" ? "bg-ink-700" : "bg-ink-800"}`}>Preset</button>
        <button type="button" onClick={() => onChange({ cronMode: "advanced" })}
                className={`px-2 py-1 text-xs rounded ${values.cronMode === "advanced" ? "bg-ink-700" : "bg-ink-800"}`}>Advanced</button>
      </div>
      {values.cronMode === "preset" ? (
        <select
          id={`${idPrefix}-cron-preset`}
          aria-label="Cron preset"
          value={values.presetIdx}
          onChange={(e) => onChange({ presetIdx: parseInt(e.target.value, 10) })}
          className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
        >
          {CRON_PRESETS.map((p, i) => <option key={p.cron} value={i}>{p.label}</option>)}
        </select>
      ) : (
        <input
          id={`${idPrefix}-cron-advanced`}
          aria-label="Cron expression"
          type="text"
          value={values.advancedCron}
          onChange={(e) => onChange({ advancedCron: e.target.value })}
          className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule font-mono"
        />
      )}
      <div className="text-xs text-ink-500 mt-1">{cron} — {explainCron(cron)}</div>
    </div>
  );
}

function AiModeFields({ idPrefix, values, onChange }: FieldGroupProps) {
  return (
    <fieldset className="grid grid-cols-2 gap-3 text-sm border border-rule rounded p-3">
      <legend className="px-1 text-xs text-ink-500 uppercase tracking-wide">AI mode</legend>
      <label className="flex flex-col gap-1" htmlFor={`${idPrefix}-payload-shape`}>
        <span className="text-xs text-ink-500">Payload shape</span>
        <select
          id={`${idPrefix}-payload-shape`}
          value={values.mode}
          onChange={(e) => onChange({ mode: e.target.value as ObserverMode })}
          className="px-2 py-1 rounded bg-ink-850 border border-rule"
        >
          <option value="full">Full payload</option>
          <option value="diff">Diff vs previous capture</option>
        </select>
      </label>
      <label className="flex items-center gap-2 mt-6">
        <input
          type="checkbox" checked={values.structured}
          onChange={(e) => onChange({ structured: e.target.checked })}
        />
        <span>Structured (typed observation card)</span>
      </label>
      <label className="flex items-center gap-2 col-span-2">
        <input
          type="checkbox" checked={values.useBatch}
          onChange={(e) => onChange({ useBatch: e.target.checked })}
        />
        <span>Messages Batch per watchlist ticker (50% cheaper, async; Claude only)</span>
      </label>
      <label className="flex items-center gap-2 col-span-2">
        <input
          type="checkbox" checked={values.consensus} disabled={!values.structured}
          onChange={(e) => onChange({ consensus: e.target.checked })}
        />
        <span className={values.structured ? "" : "text-ink-600"}>
          Cross-model consensus (fan structured report across providers; needs Structured; ~Nx cost)
        </span>
      </label>
      <div className="col-span-2">
        <InvestigateToggle
          idPrefix={idPrefix}
          checked={values.investigate}
          onChange={(investigate) => onChange({ investigate })}
          note={
            values.structured || values.consensus || values.useBatch
              ? "Plain fires only — structured, consensus and batch fires ignore it."
              : undefined
          }
        />
      </div>
    </fieldset>
  );
}

function ModelOverrideFields({ idPrefix, values, onChange }: FieldGroupProps) {
  const descId = `${idPrefix}-override-desc`;
  return (
    <fieldset className="border border-rule rounded p-3 space-y-2">
      <legend className="px-1 text-xs text-ink-500 uppercase tracking-wide">Model</legend>
      <label className="flex items-center gap-2 text-sm" htmlFor={`${idPrefix}-override-model`}>
        <input
          id={`${idPrefix}-override-model`}
          type="checkbox"
          checked={values.overrideModel}
          aria-describedby={descId}
          onChange={(e) => onChange({ overrideModel: e.target.checked })}
        />
        <span>Override the profile&apos;s provider / model</span>
      </label>
      <p id={descId} className="text-xs text-ink-500">
        Off: every fire uses the trading profile&apos;s own provider and model.
      </p>
      {values.overrideModel && (
        <ProviderModelPicker
          value={values.override}
          onChange={(override) => onChange({ override })}
        />
      )}
    </fieldset>
  );
}

function WatchlistFields({ idPrefix, values, onChange }: FieldGroupProps) {
  const descId = `${idPrefix}-tickers-desc`;
  return (
    <div className="space-y-1">
      <span className="block text-xs text-ink-500" id={`${idPrefix}-tickers-label`}>
        Watchlist override
      </span>
      <TickerChipsInput
        value={values.watchlistTickers}
        onChange={(watchlistTickers) => onChange({ watchlistTickers })}
        ariaLabel="Watchlist override tickers"
      />
      <p id={descId} className="text-xs text-ink-500">
        Empty — captures the profile&apos;s watchlist. Set tickers to pin this
        schedule to its own symbols (also what market-hours and batch fan-out use).
      </p>
    </div>
  );
}

export interface ScheduleFormProps {
  /** Distinguishes control ids when several forms are mounted at once. */
  idPrefix: string;
  values: ScheduleFormValues;
  onChange: ScheduleFormChange;
  profiles: TradingProfile[] | undefined;
  profileId: number | null;
  onProfileChange: (id: number) => void;
  onSubmit: (e: React.FormEvent) => void;
  submitLabel: string;
  pendingLabel: string;
  isPending: boolean;
  onCancel?: () => void;
  error?: string | null;
}

/**
 * The one schedule form. Create mounts it blank; the per-row edit expander
 * mounts it seeded from the saved schedule, so every field stays editable
 * after create.
 */
export default function ScheduleForm({
  idPrefix, values, onChange, profiles, profileId, onProfileChange,
  onSubmit, submitLabel, pendingLabel, isPending, onCancel, error,
}: ScheduleFormProps) {
  const group = { idPrefix, values, onChange };
  return (
    <form onSubmit={onSubmit} className="p-4 rounded border border-rule bg-ink-900 space-y-3">
      <div>
        <label className="block text-xs text-ink-500 mb-1" htmlFor={`${idPrefix}-name`}>Name</label>
        <input
          id={`${idPrefix}-name`}
          type="text" value={values.name} onChange={(e) => onChange({ name: e.target.value })} required
          className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule ledger-input"
        />
      </div>

      <div>
        <label className="block text-xs text-ink-500 mb-1" htmlFor={`${idPrefix}-profile`}>Profile</label>
        <select
          id={`${idPrefix}-profile`}
          value={profileId ?? ""} onChange={(e) => onProfileChange(parseInt(e.target.value, 10))}
          className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
        >
          {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-1" htmlFor={`${idPrefix}-enabled`}>
          <input
            id={`${idPrefix}-enabled`}
            type="checkbox" checked={values.enabled}
            onChange={(e) => onChange({ enabled: e.target.checked })}
          />
          enabled
        </label>
        <label className="flex items-center gap-1" htmlFor={`${idPrefix}-market-hours-only`}>
          <input
            id={`${idPrefix}-market-hours-only`}
            type="checkbox" checked={values.marketHoursOnly}
            onChange={(e) => onChange({ marketHoursOnly: e.target.checked })}
          />
          market hours only
        </label>
      </div>

      <FireModeFields {...group} />

      {values.fireMode === "cron" && <CronFields {...group} />}

      <div>
        <label className="block text-xs text-ink-500 mb-1" htmlFor={`${idPrefix}-objective`}>
          Objective template (sent with every fire)
        </label>
        <textarea
          id={`${idPrefix}-objective`}
          rows={2} value={values.objective} onChange={(e) => onChange({ objective: e.target.value })}
          className="w-full px-2 py-1.5 rounded bg-ink-850 border border-rule"
          placeholder="e.g. Flag any unusual options activity."
        />
      </div>

      <WatchlistFields {...group} />

      <ModelOverrideFields {...group} />

      <AiModeFields {...group} />

      {error && (
        <div role="alert" className="text-xs text-loss-400">{error}</div>
      )}

      <div className="flex gap-2">
        <button type="submit" disabled={isPending || !values.name || !profileId}
                className="px-3 py-1.5 rounded bg-gain-500 hover:bg-gain-400 disabled:opacity-40">
          {isPending ? pendingLabel : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}
                  className="px-3 py-1.5 rounded bg-ink-800 hover:bg-ink-700">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
