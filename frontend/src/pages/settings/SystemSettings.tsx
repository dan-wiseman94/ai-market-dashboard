import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSystemSettings } from "@/hooks/useSystemSettings";
import { updateSystemSettings, type SystemSettings as Settings } from "@/api/settings";
import SettingsSection from "@/components/settings/SettingsSection";
import { useToast } from "@/hooks/useToast";

type NumericKey =
  | "retention_ohlc_days"
  | "retention_chain_days"
  | "retention_notification_days"
  | "retention_error_days"
  | "observer_response_cache_ttl_seconds"
  | "aieval_scheduled_horizon"
  | "aieval_scheduled_limit";

export default function SystemSettings() {
  const { data, isLoading } = useSystemSettings();
  const { push } = useToast();
  const qc = useQueryClient();
  // Draft overlay on top of the server data — derive effective values in render so we never
  // setState in an effect (react-hooks/set-state-in-effect is an error here).
  const [draft, setDraft] = useState<Partial<Settings>>({});
  const [saving, setSaving] = useState(false);

  if (isLoading || !data) {
    return (
      <SettingsSection title="System" description="Runtime knobs — take effect without a restart.">
        <p className="text-ink-400 text-sm">Loading…</p>
      </SettingsSection>
    );
  }

  const eff = { ...data, ...draft };
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const onSave = async () => {
    if (Object.keys(draft).length === 0) return;
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

  const num = (key: NumericKey, label: string, hint?: string) => (
    <label className="grid gap-1">
      <span className="text-[12px] text-ink-300">{label}</span>
      <input
        type="number"
        min={0}
        aria-label={label}
        value={String(eff[key])}
        onChange={(e) => set(key, Number(e.target.value) as Settings[NumericKey])}
        className="ledger-input w-40 py-2 tabular-nums"
      />
      {hint && <span className="text-[11px] text-ink-500">{hint}</span>}
    </label>
  );

  const bool = (key: keyof Settings, label: string) => (
    <label className="flex items-center gap-2">
      <input
        type="checkbox"
        aria-label={label}
        checked={Boolean(eff[key])}
        onChange={(e) => set(key, e.target.checked as Settings[keyof Settings])}
      />
      <span className="text-[13px] text-ink-200">{label}</span>
    </label>
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
        </div>
      </div>

      <div className="ledger-surface p-5">
        <h3 className="font-display text-[1.05rem] text-ink-50">AI failover</h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Retry on a secondary provider when the primary errors before streaming.</p>
        <div className="grid gap-3">
          {bool("ai_failover_enabled", "Enable failover")}
          <label className="grid gap-1">
            <span className="text-[12px] text-ink-300">Failover provider</span>
            <input
              type="text"
              aria-label="Failover provider"
              value={eff.ai_failover_provider}
              onChange={(e) => set("ai_failover_provider", e.target.value)}
              placeholder="e.g. openai"
              className="ledger-input w-56 py-2 font-mono text-[12px]"
            />
          </label>
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
        <h3 className="font-display text-[1.05rem] text-ink-50">Scheduled eval <span className="text-ink-500 text-[12px]">· advanced</span></h3>
        <p className="mt-1 mb-3 text-[12px] text-ink-400">Offline calibration replay. Enabling it makes real (billed) model calls on a schedule.</p>
        <div className="grid gap-3">
          {bool("aieval_scheduled_enabled", "Enable scheduled eval")}
          <label className="grid gap-1">
            <span className="text-[12px] text-ink-300">Model</span>
            <input
              type="text"
              aria-label="Eval model"
              value={eff.aieval_scheduled_model}
              onChange={(e) => set("aieval_scheduled_model", e.target.value)}
              className="ledger-input w-56 py-2 font-mono text-[12px]"
            />
          </label>
          <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
            {num("aieval_scheduled_horizon", "Horizon (days)")}
            {num("aieval_scheduled_limit", "Row limit")}
          </div>
        </div>
      </div>
    </SettingsSection>
  );
}
