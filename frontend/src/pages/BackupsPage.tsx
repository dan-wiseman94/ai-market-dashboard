import { useState } from "react";
import { useBackups, useDeleteBackup, useRunBackupNow } from "@/hooks/useBackups";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function BackupsPage() {
  const { data = [], isLoading } = useBackups();
  const { push } = useToast();
  const run = useRunBackupNow();
  const del = useDeleteBackup();
  const [confirm, setConfirm] = useState<number | null>(null);

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backups</h1>
        <button
          className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-sm disabled:opacity-50"
          disabled={run.isPending}
          onClick={() => run.mutate(undefined, {
            onSuccess: () => push({ kind: "info", text: "Backup queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {run.isPending ? "Queuing…" : "Back up now ↻"}
        </button>
      </div>
      <p className="text-xs text-slate-500">Daily at 02:30 UTC · keep last 7 scheduled</p>

      {isLoading && <SkeletonRows rows={4} />}
      {!isLoading && data.length === 0 && (
        <EmptyState title="No backups yet" body="The nightly job will create one at 02:30 UTC." />
      )}

      {data.length > 0 && (
      <table className="w-full text-sm border border-slate-800 rounded overflow-hidden">
        <thead className="bg-slate-900 text-slate-400 text-left">
          <tr>
            <th className="px-2 py-1.5">Created</th>
            <th className="px-2 py-1.5">Filename</th>
            <th className="px-2 py-1.5">Size</th>
            <th className="px-2 py-1.5">Kind</th>
            <th className="px-2 py-1.5">Status</th>
            <th className="px-2 py-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {data.map((b) => (
            <tr key={b.id} className={`border-t border-slate-800 ${b.status !== "ok" ? "opacity-60" : ""}`}>
              <td className="px-2 py-1.5">{new Date(b.created_at).toLocaleString()}</td>
              <td className="px-2 py-1.5 font-mono text-xs">{b.filename}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmtSize(b.size_bytes)}</td>
              <td className="px-2 py-1.5">{b.kind}</td>
              <td className="px-2 py-1.5">
                {b.status === "failed" ? (
                  <span title={b.error} className="text-rose-400">✗ failed</span>
                ) : b.status}
              </td>
              <td className="px-2 py-1.5 text-right">
                {b.status === "ok" && (
                  <>
                    <a className="text-emerald-300 hover:underline text-xs mr-3"
                       href={`/api/backups/${b.id}/download/`}>Download</a>
                    <button className="text-rose-400 hover:underline text-xs"
                            onClick={() => setConfirm(b.id)}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}

      {confirm !== null && (
        <div role="dialog" aria-modal="true" aria-label="Confirm delete backup"
             className="fixed inset-0 bg-black/70 grid place-items-center z-50"
             onClick={() => setConfirm(null)}>
          <div className="bg-slate-950 border border-slate-700 rounded p-4 w-96"
               tabIndex={-1}
               onClick={(e) => e.stopPropagation()}>
            <p>Delete this backup? The file on disk will be removed.</p>
            <div className="flex justify-end gap-2 mt-3">
              <button className="px-3 py-1 rounded bg-slate-700" onClick={() => setConfirm(null)}>Cancel</button>
              <button className="px-3 py-1 rounded bg-rose-600"
                      onClick={() => {
                        del.mutate(confirm, {
                          onSuccess: () => push({ kind: "success", text: "Backup deleted." }),
                          onError: (e) => push({ kind: "error", text: (e as Error).message }),
                        });
                        setConfirm(null);
                      }}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
