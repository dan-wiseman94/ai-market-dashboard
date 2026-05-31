import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDataSources } from "@/hooks/useDataSources";
import {
  saveDataSourceKey,
  clearDataSourceKey,
  testDataSourceKey,
  type DataSource,
  type TestResult,
} from "@/api/dataSources";
import { useToast } from "@/hooks/useToast";
import { SkeletonRows } from "@/components/Skeleton";

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
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const keyed = ds.auth === "key" || ds.auth === "key_secret";

  // Shared busy/error scaffolding so save/clear/test only carry their own body.
  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    withBusy(async () => {
      setTestResult(null);
      const body: Record<string, string> = {};
      for (const f of ds.fields) if (values[f]) body[`${f}_write`] = values[f];
      await saveDataSourceKey(ds.provider, body);
      setValues({});
      onChanged();
      push({ kind: "success", text: `${ds.label} saved.` });
    });

  const clear = () =>
    withBusy(async () => {
      setTestResult(null);
      await clearDataSourceKey(ds.provider);
      setValues({});
      onChanged();
      push({ kind: "success", text: `${ds.label} cleared.` });
    });

  const test = () =>
    withBusy(async () => {
      const res = await testDataSourceKey(ds.provider);
      setTestResult(res);
      push({ kind: res.ok ? "success" : "error", text: `${ds.label}: ${res.message}` });
    });

  return (
    <div className="ledger-surface p-5" data-testid={`ds-card-${ds.provider}`}>
      <div className="flex items-center gap-3">
        <h4 className="font-display text-[1rem] text-ink-50">{ds.label}</h4>
        <StatusPill ds={ds} />
      </div>
      <p className="mt-2 text-[13px] text-ink-300">{ds.blurb}</p>

      {ds.auth === "none" && (
        <p className="mt-3 text-[12px] text-ink-400">Ready to use — no key required.</p>
      )}

      {keyed && (
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
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={save} disabled={busy} className="ledger-cta">
              {busy ? "Saving…" : "Save"}
            </button>
            {ds.status.configured && (
              <>
                <button
                  type="button"
                  onClick={test}
                  disabled={busy}
                  className="text-[12px] text-copper-300 hover:text-copper-200"
                >
                  Test key
                </button>
                <button
                  type="button"
                  onClick={clear}
                  disabled={busy}
                  className="text-[12px] text-ink-400 hover:text-ink-200"
                >
                  Clear
                </button>
              </>
            )}
            {testResult && (
              <span className="ledger-pill" data-tone={testResult.ok ? "gain" : "loss"}>
                {testResult.message}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="mt-3 flex items-center gap-4">
        {keyed && ds.signup_url && (
          <a
            href={ds.signup_url}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[11px] text-copper-300 hover:text-copper-200"
          >
            Get a free key ↗
          </a>
        )}
        <a
          href={ds.docs_url}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[11px] text-ink-500 hover:text-copper-300"
        >
          docs ↗
        </a>
      </div>
    </div>
  );
}

/** The list of free / key-based market-data providers, embedded on the Connections tab.
 *  Schwab (auth "oauth") is excluded — it has its own OAuth connect card above this. */
export default function DataSourcesPanel() {
  const { data, isLoading } = useDataSources();
  const qc = useQueryClient();
  const onChanged = () => {
    void qc.invalidateQueries({ queryKey: ["data-sources"] });
  };
  const sources = (data?.data_sources ?? []).filter((ds) => ds.auth !== "oauth");

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-3">
        <h3 className="font-display text-[1.1rem] text-ink-50">Free data sources</h3>
        <span className="text-[12px] text-ink-400">Optional providers that run alongside Schwab.</span>
      </div>
      {isLoading ? (
        <SkeletonRows rows={4} />
      ) : (
        sources.map((ds) => <DataSourceCard key={ds.provider} ds={ds} onChanged={onChanged} />)
      )}
    </div>
  );
}
