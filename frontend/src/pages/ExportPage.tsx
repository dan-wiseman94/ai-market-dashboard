import { useState } from "react";
import { useCreateExport, useDeleteExport, useExports } from "@/hooks/useExport";
import type { ExportJob, ExportScope } from "@/api/export";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import SettingsSection from "@/components/settings/SettingsSection";

const ONE_GB = 1024 * 1024 * 1024;

function fmtSize(n: number | null): string {
  if (!n) return "—";
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function ExportPage() {
  const { data = [], isLoading } = useExports();
  const { push } = useToast();
  const create = useCreateExport();
  const del = useDeleteExport();
  const [scope, setScope] = useState<ExportScope>({
    threads: "all", snapshots: "all",
    observations: true, triggers: true, profiles: true, watchlists: true,
  });

  const totalBytes = data.filter((j) => j.status === "done").reduce((acc, j) => acc + (j.size_bytes ?? 0), 0);
  const overThreshold = totalBytes > ONE_GB;
  const anyRunning = data.some((j) => j.status === "pending" || j.status === "running");

  return (
    <SettingsSection title="Export" description="Bundle your data into a downloadable zip.">
      {overThreshold && (
        <div className="ledger-surface px-4 py-3 text-[13px] text-copper-200"
             style={{ borderColor: "var(--rule-strong)" }}>
          Exports currently occupy {fmtSize(totalBytes)}. Consider deleting old ones.
        </div>
      )}

      <div className="ledger-surface p-5 space-y-3">
        <h3 className="ledger-eyebrow">Choose what to include</h3>
        <div className="grid sm:grid-cols-2 gap-2">
          <ScopeCheck label="Threads (all)" checked={!!scope.threads}
                      onChange={(v) => setScope((s) => ({ ...s, threads: v ? "all" : undefined }))} />
          <ScopeCheck label="Snapshots (all)" checked={!!scope.snapshots}
                      onChange={(v) => setScope((s) => ({ ...s, snapshots: v ? "all" : undefined }))} />
          <ScopeCheck label="Observations" checked={!!scope.observations}
                      onChange={(v) => setScope((s) => ({ ...s, observations: v }))} />
          <ScopeCheck label="Triggers + firings" checked={!!scope.triggers}
                      onChange={(v) => setScope((s) => ({ ...s, triggers: v }))} />
          <ScopeCheck label="Profiles + Watchlists" checked={!!scope.profiles && !!scope.watchlists}
                      onChange={(v) => setScope((s) => ({ ...s, profiles: v, watchlists: v }))} />
        </div>
        <button
          className="ledger-cta disabled:opacity-50"
          disabled={create.isPending || anyRunning}
          onClick={() => create.mutate(scope, {
            onSuccess: () => push({ kind: "info", text: "Export job queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {create.isPending ? "Queuing…" : "Start export"}
        </button>
      </div>

      <div>
        <h3 className="ledger-eyebrow mb-2">Recent exports</h3>
        {isLoading && <SkeletonRows rows={3} />}
        {!isLoading && data.length === 0 && (
          <EmptyState
            title="No exports yet"
            body="Pick what you'd like to bundle, then start an export. The zip builds asynchronously."
          />
        )}
        {data.length > 0 && (
          <div className="ledger-surface overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-rule text-left">
                  {["Created", "Status", "Size", "Filename", ""].map((h, i) => (
                    <th key={i} className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-copper-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {data.map((j) => (
                  <tr key={j.id} data-testid={`export-row-${j.id}`}>
                    <td className="px-4 py-2.5 text-ink-300">{new Date(j.created_at).toLocaleString()}</td>
                    <td className="px-4 py-2.5">
                      <JobStatusBadge status={j.status} error={j.error} />
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-ink-200">{fmtSize(j.size_bytes)}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-ink-200">{j.filename}</td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      {j.status === "done" && (
                        <>
                          <a className="text-copper-300 hover:text-copper-200 text-[12px] mr-4"
                             href={`/api/export/${j.id}/download/`}>Download</a>
                          <button className="text-loss hover:underline text-[12px]"
                                  onClick={() => del.mutate(j.id)}>Delete</button>
                        </>
                      )}
                      {j.status === "failed" && (
                        <button className="text-copper-300 hover:text-copper-200 text-[12px]"
                                onClick={() => create.mutate(j.scope as ExportScope)}>Retry</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SettingsSection>
  );
}

function JobStatusBadge({ status, error }: { status: ExportJob["status"]; error: string }) {
  if (status === "running" || status === "pending") {
    return <span className="text-copper-300">{status}…</span>;
  }
  if (status === "done") {
    return <span className="text-gain">done</span>;
  }
  return <span className="text-loss" title={error}>{status}</span>;
}

function ScopeCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-[13px] text-ink-200">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="accent-[var(--copper-500)]" />
      <span>{label}</span>
    </label>
  );
}
