import { useState } from "react";
import { useCreateExport, useDeleteExport, useExports } from "@/hooks/useExport";
import type { ExportScope } from "@/api/export";

const ONE_GB = 1024 * 1024 * 1024;

function fmtSize(n: number | null): string {
  if (!n) return "—";
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function ExportPage() {
  const { data = [], isLoading } = useExports();
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
    <main className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">Export</h1>

      {overThreshold && (
        <div className="px-3 py-2 rounded bg-amber-900/40 border border-amber-700 text-sm text-amber-200">
          Exports currently occupy {fmtSize(totalBytes)}. Consider deleting old ones.
        </div>
      )}

      <section className="border border-slate-800 rounded p-4 space-y-2">
        <h2 className="text-sm uppercase text-slate-500">Choose what to include</h2>
        <Toggle label="Threads (all)" checked={!!scope.threads}
                onChange={(v) => setScope((s) => ({ ...s, threads: v ? "all" : undefined }))} />
        <Toggle label="Snapshots (all)" checked={!!scope.snapshots}
                onChange={(v) => setScope((s) => ({ ...s, snapshots: v ? "all" : undefined }))} />
        <Toggle label="Observations" checked={!!scope.observations}
                onChange={(v) => setScope((s) => ({ ...s, observations: v }))} />
        <Toggle label="Triggers + firings" checked={!!scope.triggers}
                onChange={(v) => setScope((s) => ({ ...s, triggers: v }))} />
        <Toggle label="Profiles + Watchlists" checked={!!scope.profiles && !!scope.watchlists}
                onChange={(v) => setScope((s) => ({ ...s, profiles: v, watchlists: v }))} />
        <button
          className="mt-2 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-sm disabled:opacity-50"
          disabled={create.isPending || anyRunning}
          onClick={() => create.mutate(scope)}
        >
          {create.isPending ? "Queuing…" : "Start export"}
        </button>
      </section>

      <section>
        <h2 className="text-sm uppercase text-slate-500 mb-2">Recent exports</h2>
        {isLoading && <div className="text-slate-500">Loading…</div>}
        <table className="w-full text-sm border border-slate-800 rounded">
          <thead className="bg-slate-900 text-slate-400 text-left">
            <tr>
              <th className="px-2 py-1.5">Created</th>
              <th className="px-2 py-1.5">Status</th>
              <th className="px-2 py-1.5">Size</th>
              <th className="px-2 py-1.5">Filename</th>
              <th className="px-2 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {data.map((j) => (
              <tr key={j.id} className="border-t border-slate-800">
                <td className="px-2 py-1.5">{new Date(j.created_at).toLocaleString()}</td>
                <td className="px-2 py-1.5">
                  {j.status === "running" || j.status === "pending"
                    ? <span className="text-amber-300">{j.status}…</span>
                    : j.status === "done" ? "done"
                    : <span className="text-rose-400" title={j.error}>{j.status}</span>}
                </td>
                <td className="px-2 py-1.5 tabular-nums">{fmtSize(j.size_bytes)}</td>
                <td className="px-2 py-1.5 font-mono text-xs">{j.filename}</td>
                <td className="px-2 py-1.5 text-right">
                  {j.status === "done" && (
                    <>
                      <a className="text-emerald-300 hover:underline text-xs mr-3"
                         href={`/api/export/${j.id}/download/`}>Download</a>
                      <button className="text-rose-400 hover:underline text-xs"
                              onClick={() => del.mutate(j.id)}>Delete</button>
                    </>
                  )}
                  {j.status === "failed" && (
                    <button
                      className="text-amber-300 hover:underline text-xs"
                      onClick={() => create.mutate(j.scope as ExportScope)}
                    >Retry</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}
