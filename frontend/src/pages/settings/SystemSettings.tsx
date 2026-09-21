import { useId, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSystemSettings } from "@/hooks/useSystemSettings";
import { updateSystemSettings, type SystemSettings as Settings } from "@/api/settings";
import SettingsSection from "@/components/settings/SettingsSection";
import { SkeletonRows } from "@/components/Skeleton";
import ProviderSelect from "@/components/ai/ProviderSelect";
import ModelSelect from "@/components/settings/ModelSelect";
import { useCatalog } from "@/hooks/useCatalog";
import { FALLBACK_HORIZONS } from "@/lib/horizons";
import { useToast } from "@/hooks/useToast";

// The numeric-valued keys of Settings, derived from the interface so it can't drift.
type NumericKey = { [K in keyof Settings]: Settings[K] extends number ? K : never }[keyof Settings];

// Three knobs here cost something irreversible, so each one asks before it is armed:
// total-return math restates numbers already recorded, and the two background jobs bill
// real model calls on a schedule without anyone watching.
const DIVIDEND_CONFIRM =
  "Dividend-adjusted returns are retroactive: every post-mortem, Scorecard and Mirror " +
  "number already computed under price-return will be restated. Switch methodology?";

const SWEEP_CONFIRM =
  "Arm the scheduled anomaly sweep? It runs on its own and opens bounded autonomous " +
  "investigations — several billed model calls each, on your own API key. Spend is bounded " +
  "by the autonomous daily cap and the desk's daily origination cap, not by this switch.";

const SCHEDULED_EVAL_CONFIRM =
  "Enable scheduled eval? Every scheduled run makes real, billed model calls — one per " +
  "replayed snapshot, up to the row limit — on your own API key. There is no mocked path: " +
  "the scheduled run reaches the real model even on a mock-mode stack.";

// Retention days are the only destructive control on this page: the nightly purge acts on
// whatever window is saved, and captured bars and chains have no re-fetch path.
const RETENTION_FIELDS: ReadonlyArray<{ key: NumericKey; label: string }> = [
  { key: "retention_ohlc_days", label: "OHLC bars" },
  { key: "retention_chain_days", label: "Option chains" },
  { key: "retention_notification_days", label: "Notifications" },
  { key: "retention_error_days", label: "Resolved errors" },
  { key: "retention_regime_days", label: "Regime readings" },
  { key: "retention_desk_days", label: "Desk findings" },
  { key: "retention_book_days", label: "Book snapshots" },
];

function purgeConfirm(cuts: ReadonlyArray<{ label: string; from: number; to: number }>): string {
  const lines = cuts.map((c) => `• ${c.label}: ${c.from} → ${c.to} days`).join("\n");
  return (
    `Shortening a retention window deletes the rows that fall outside it at the next ` +
    `nightly purge, permanently:\n\n${lines}\n\n` +
    "Stored bars and chains are what post-mortems, the Scorecard and trigger backtests read, " +
    "and nothing re-fetches them. Save anyway?"
  );
}

export default function SystemSettings() {
  const { data, isLoading } = useSystemSettings();
  const { defaultFor } = useCatalog();
  const { push } = useToast();
  const qc = useQueryClient();
  // Draft overlay on top of the server data — derive effective values in render so we never
  // setState in an effect (react-hooks/set-state-in-effect is an error here).
  const [draft, setDraft] = useState<Partial<Settings>>({});
  const [saving, setSaving] = useState(false);
  const uid = useId();

  if (isLoading || !data) {
    return (
      <SettingsSection title="System" description="Runtime knobs — take effect without a restart.">
        <SkeletonRows rows={6} />
      </SettingsSection>
    );
  }

  const eff = { ...data, ...draft };
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const cuts = RETENTION_FIELDS.flatMap(({ key, label }) => {
    const next = draft[key];
    return typeof next === "number" && next < data[key]
      ? [{ label, from: data[key], to: next }]
      : [];
  });

  const onSave = async () => {
    if (Object.keys(draft).length === 0) return;
    if (cuts.length > 0 && !window.confirm(purgeConfirm(cuts))) return;
    setSaving(true);
    try {
      await updateSystemSettings(draft);
      setDraft({});
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
      push({ kind: "success", text: "Settings saved." });
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  // Hints hang off aria-describedby, never aria-label: an aria-label wins the
  // accessible-name computation outright, so a hint folded into the label element
  // would be dropped by a screen reader instead of read after the name. The field
  // key is unique per control, so one useId prefix yields stable unique ids.
  const fieldId = (key: keyof Settings) => `${uid}-${key}`;
  const hintId = (key: keyof Settings) => `${uid}-${key}-hint`;

  const num = (key: NumericKey, label: string, hint?: string, step?: number) => (
    <div className="grid gap-1">
      <label htmlFor={fieldId(key)} className="text-[12px] text-ink-300">
        {label}
      </label>
      <input
        id={fieldId(key)}
        type="number"
        min={0}
        step={step ?? 1}
        aria-describedby={hint ? hintId(key) : undefined}
        value={String(eff[key])}
        onChange={(e) => set(key, Number(e.target.value) as Settings[NumericKey])}
        className="ledger-input w-40 py-2 tabular-nums"
      />
      {hint && (
        <span id={hintId(key)} className="text-[11px] text-ink-500">
          {hint}
        </span>
      )}
    </div>
  );

  const bool = (key: keyof Settings, label: string, hint?: string) => (
    <div className="grid gap-0.5">
      <div className="flex items-start gap-2">
        <input
          id={fieldId(key)}
          type="checkbox"
          aria-describedby={hint ? hintId(key) : undefined}
          checked={Boolean(eff[key])}
          onChange={(e) => set(key, e.target.checked as Settings[keyof Settings])}
          className="mt-[3px]"
        />
        <label htmlFor={fieldId(key)} className="text-[13px] text-ink-200">
          {label}
        </label>
      </div>
      {hint && (
        <span id={hintId(key)} className="pl-6 text-[11px] text-ink-500">
          {hint}
        </span>
      )}
    </div>
  );

  // Same control, but arming it asks first. Declining leaves state untouched; React
  // restores the checkbox to the controlled value on the no-op render.
  const boolConfirm = (key: keyof Settings, label: string, message: string, hint?: string) => (
    <div className="grid gap-0.5">
      <div className="flex items-start gap-2">
        <input
          id={fieldId(key)}
          type="checkbox"
          aria-describedby={hint ? hintId(key) : undefined}
          checked={Boolean(eff[key])}
          onChange={(e) => {
            if (e.target.checked && !window.confirm(message)) return;
            set(key, e.target.checked as Settings[keyof Settings]);
          }}
          className="mt-[3px]"
        />
        <label htmlFor={fieldId(key)} className="text-[13px] text-ink-200">
          {label}
        </label>
      </div>
      {hint && (
        <span id={hintId(key)} className="pl-6 text-[11px] text-ink-500">
          {hint}
        </span>
      )}
    </div>
  );

  return (
    <SettingsSection
      title="System"
      description="Runtime knobs — saved values take effect on the next task run, no restart."
      action={
        <button type="button" onClick={onSave} disabled={saving || Object.keys(draft).length === 0} className="ledger-cta">
          {saving ? "Saving…" : "Save changes"}
        </button>
      }
    >
      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Data retention</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">How long captured market data and logs are kept before the nightly purge.</p>
        <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
          {num("retention_ohlc_days", "OHLC bars (days)")}
          {num("retention_chain_days", "Option chains (days)")}
          {num("retention_notification_days", "Notifications (days)")}
          {num("retention_error_days", "Resolved errors (days)")}
          {num("retention_regime_days", "Regime readings (days)")}
          {num("retention_desk_days", "Desk findings (days)")}
          {num("retention_book_days", "Book snapshots (days)")}
        </div>
        {cuts.length > 0 && (
          <p role="status" className="mt-3 text-[12px] text-copper-400">
            Shortening a window deletes the rows outside it at the next nightly purge, and
            nothing re-fetches them: {cuts.map((c) => `${c.label} ${c.from}→${c.to}`).join(", ")}.
          </p>
        )}
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">AI failover</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Retry on a secondary provider when the primary errors before streaming.</p>
        <div className="grid gap-3">
          {bool("ai_failover_enabled", "Enable failover")}
          <div className="grid gap-1">
            <label htmlFor={fieldId("ai_failover_provider")} className="text-[12px] text-ink-300">
              Failover provider
            </label>
            {/* A list, not free text: a typo'd provider id silently disables failover. */}
            <ProviderSelect
              id={fieldId("ai_failover_provider")}
              emptyOption="None"
              value={eff.ai_failover_provider}
              onChange={(p) => set("ai_failover_provider", p)}
              className="w-56"
            />
          </div>
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Observer response cache</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Reuse a recent observation when the prompt is byte-identical within the TTL.</p>
        <div className="grid gap-3">
          {bool("observer_response_cache_enabled", "Enable response cache")}
          {num("observer_response_cache_ttl_seconds", "Cache TTL (seconds)")}
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Autonomous AI <span className="text-ink-500 text-[12px]">· spend bounds</span></h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Background runs and the ceilings that bound what any one run can spend.</p>
        <div className="grid gap-3">
          {boolConfirm(
            "anomaly_sweep_enabled",
            "Scheduled anomaly sweep",
            SWEEP_CONFIRM,
            "Scans watched tickers every 30 min and opens Desk investigations on its own — " +
              "several billed model calls per investigation, under the cap below.",
          )}
          <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
            {num(
              "ai_autonomous_daily_cap_usd",
              "Autonomous daily cap (USD)",
              "0 removes this ceiling — only the provider's own daily cap then applies.",
              0.01,
            )}
            {num("ai_investigation_max_iterations", "Investigation tool rounds")}
            {num("ai_chat_max_tool_iterations", "Chat tool rounds")}
          </div>
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Calibration &amp; routing</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Use measured accuracy to pick the fallback model, and get told when a model drifts.</p>
        <div className="grid gap-3">
          {bool(
            "ai_calibration_routing_enabled",
            "Route by measured calibration",
            "Only the fallback tier — a per-send override or a profile's pinned model still wins.",
          )}
          {bool(
            "calibration_drift_sentinel_enabled",
            "Alert on calibration drift",
            "Daily check over stored eval runs; notifies once per drift episode. No AI spend.",
          )}
          <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
            {num(
              "ai_calibration_routing_min_scored",
              "Min scored calls",
              "Below this, routing ignores the measurement as too thin.",
            )}
            {num(
              "ai_calibration_routing_max_age_days",
              "Max eval age (days)",
              "Older evals don't pin routing.",
            )}
          </div>
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Scheduled eval <span className="text-ink-500 text-[12px]">· advanced</span></h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Replays frozen snapshots of decisive theses through the chosen provider and scores its directional calls. Enabling it makes real (billed) model calls on a schedule.</p>
        <div className="grid gap-3">
          {boolConfirm(
            "aieval_scheduled_enabled",
            "Enable scheduled eval",
            SCHEDULED_EVAL_CONFIRM,
            "One billed model call per replayed snapshot, up to the row limit, every run. " +
              "There is no mocked path — it reaches the real model even on a mock-mode stack.",
          )}
          <div className="grid gap-1">
            <label htmlFor={fieldId("aieval_scheduled_provider")} className="text-[12px] text-ink-300">
              Eval provider
            </label>
            <ProviderSelect
              id={fieldId("aieval_scheduled_provider")}
              value={eff.aieval_scheduled_provider}
              onChange={(p) => {
                // A model id belongs to one vendor, so a provider change must carry the
                // model with it — the backend would otherwise repair it silently.
                set("aieval_scheduled_provider", p);
                set("aieval_scheduled_model", defaultFor(p));
              }}
              className="w-56"
            />
          </div>
          <div className="grid gap-1">
            <label htmlFor={fieldId("aieval_scheduled_model")} className="text-[12px] text-ink-300">
              Eval model
            </label>
            <div className="w-full max-w-sm">
              <ModelSelect
                id={fieldId("aieval_scheduled_model")}
                provider={eff.aieval_scheduled_provider}
                value={eff.aieval_scheduled_model}
                onChange={(m) => set("aieval_scheduled_model", m)}
                facts
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
            <div className="grid gap-1">
              <label htmlFor={fieldId("aieval_scheduled_horizon")} className="text-[12px] text-ink-300">
                Horizon (days)
              </label>
              <select
                id={fieldId("aieval_scheduled_horizon")}
                aria-describedby={hintId("aieval_scheduled_horizon")}
                value={String(eff.aieval_scheduled_horizon)}
                onChange={(e) => set("aieval_scheduled_horizon", Number(e.target.value))}
                className="ledger-input w-40 py-2 tabular-nums"
              >
                {FALLBACK_HORIZONS.map((h) => (
                  <option key={h} value={h}>{h}</option>
                ))}
              </select>
              <span id={hintId("aieval_scheduled_horizon")} className="text-[11px] text-ink-500">
                Matches the post-mortem horizons.
              </span>
            </div>
            {num(
              "aieval_scheduled_limit",
              "Row limit",
              "Theses replayed per run — each one is a billed call.",
            )}
          </div>
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Return math</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Splits are always adjusted. Dividends are the methodology choice.</p>
        {boolConfirm(
          "returns_adjust_dividends",
          "Dividend-adjusted (total-return) math",
          DIVIDEND_CONFIRM,
          "Retroactive: it restates post-mortem, Scorecard and Mirror numbers already recorded.",
        )}
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">Backup restore</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Restoring overwrites the live database with a dump — the one destructive action here.</p>
        {bool(
          "restore_from_ui_enabled",
          "Allow restore from the UI",
          "Off leaves `make restore` as the only path.",
        )}
      </div>
    </SettingsSection>
  );
}
