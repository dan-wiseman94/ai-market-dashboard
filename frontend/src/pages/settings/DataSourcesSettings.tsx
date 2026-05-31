import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import SettingsSection from "@/components/settings/SettingsSection";
import { useDataSources } from "@/hooks/useDataSources";
import { saveDataSourceKey, clearDataSourceKey, type DataSource } from "@/api/dataSources";
import { useToast } from "@/hooks/useToast";

function fieldLabel(field: string): string {
  return field === "api_secret" ? "API secret" : "API key";
}

function StatusPill({ ds }: { ds: DataSource }) {
  const configured = ds.status.configured;
  const label = ds.auth === "none" ? "No key needed" : configured ? "Connected" : "Not connected";
  return (
    <span className="ledger-pill" data-tone={configured ? "gain" : "loss"}>
      {label}
    </span>
  );
}

function DataSourceCard({ ds, onChanged }: { ds: DataSource; onChanged: () => void }) {
  const { push } = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, string> = {};
      for (const f of ds.fields) if (values[f]) body[`${f}_write`] = values[f];
      await saveDataSourceKey(ds.provider, body);
      setValues({});
      onChanged();
      push({ kind: "success", text: `${ds.label} saved.` });
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    try {
      await clearDataSourceKey(ds.provider);
      setValues({});
      onChanged();
      push({ kind: "success", text: `${ds.label} cleared.` });
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ledger-surface p-5" data-testid={`ds-card-${ds.provider}`}>
      <div className="flex items-center gap-3">
        <h3 className="font-display text-[1.05rem] text-ink-50">{ds.label}</h3>
        <StatusPill ds={ds} />
      </div>
      <p className="mt-2 text-[13px] text-ink-300">{ds.blurb}</p>

      {ds.auth === "oauth" && (
        <p className="mt-3 text-[12px] text-ink-400">
          Connect via OAuth on the{" "}
          <Link to="/settings/connections" className="text-copper-300 hover:text-copper-200">
            Connections
          </Link>{" "}
          tab.
        </p>
      )}

      {ds.auth === "none" && (
        <p className="mt-3 text-[12px] text-ink-400">Ready to use — no key required.</p>
      )}

      {(ds.auth === "key" || ds.auth === "key_secret") && (
        <div className="mt-4 grid gap-3">
          {ds.fields.map((f) => (
            <label key={f} className="grid gap-1">
              <span className="text-[12px] text-ink-300">{fieldLabel(f)}</span>
              <input
                type="password"
                aria-label={`${ds.label} ${fieldLabel(f)}`}
                value={values[f] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
                placeholder={
                  ds.status.fields_present.includes(f) ? "•••••••• (unchanged)" : "paste your key"
                }
                className="ledger-input w-full py-2 font-mono text-[12px]"
              />
            </label>
          ))}
          <div className="flex items-center gap-3">
            <button type="button" onClick={save} disabled={busy} className="ledger-cta">
              {busy ? "Saving…" : "Save"}
            </button>
            {ds.status.configured && (
              <button
                type="button"
                onClick={clear}
                disabled={busy}
                className="text-[12px] text-ink-400 hover:text-ink-200"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      <a
        href={ds.docs_url}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-block font-mono text-[11px] text-ink-500 hover:text-copper-300"
      >
        docs ↗
      </a>
    </div>
  );
}

export default function DataSourcesSettings() {
  const { data, isLoading } = useDataSources();
  const qc = useQueryClient();
  const onChanged = () => {
    void qc.invalidateQueries({ queryKey: ["data-sources"] });
  };

  return (
    <SettingsSection
      title="Data sources"
      description="Connect free market-data providers alongside Schwab. Most run on a free API key; a couple need none."
    >
      {isLoading ? (
        <p className="text-ink-400 text-sm">Loading…</p>
      ) : (
        (data?.data_sources ?? []).map((ds) => (
          <DataSourceCard key={ds.provider} ds={ds} onChanged={onChanged} />
        ))
      )}
    </SettingsSection>
  );
}
