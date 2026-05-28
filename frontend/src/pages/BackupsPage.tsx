import { useState } from "react";
import { useBackups, useDeleteBackup, useRunBackupNow } from "@/hooks/useBackups";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import SettingsSection from "@/components/settings/SettingsSection";

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
    <SettingsSection
      title="Backups"
      description="Daily at 02:30 UTC · keep last 7 scheduled."
      action={
        <button
          className="ledger-cta disabled:opacity-50"
          disabled={run.isPending}
          onClick={() => run.mutate(undefined, {
            onSuccess: () => push({ kind: "info", text: "Backup queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {run.isPending ? "Queuing…" : "Back up now"}
        </button>
      }
    >
      {isLoading && <SkeletonRows rows={4} />}
      {!isLoading && data.length === 0 && (
        <EmptyState title="No backups yet" body="The nightly job will create one at 02:30 UTC." />
      )}

      {data.length > 0 && (
        <div className="ledger-surface overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-rule text-left">
                {["Created", "Filename", "Size", "Kind", "Status", ""].map((h, i) => (
                  <th key={i} className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-copper-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule-soft">
              {data.map((b) => (
                <tr key={b.id} data-testid={`backup-row-${b.id}`} className={b.status !== "ok" ? "opacity-60" : ""}>
                  <td className="px-4 py-2.5 text-ink-300">{new Date(b.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-ink-200">{b.filename}</td>
                  <td className="px-4 py-2.5 tabular-nums text-ink-200">{fmtSize(b.size_bytes)}</td>
                  <td className="px-4 py-2.5">
                    <span className="ledger-pill">{b.kind}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    {b.status === "failed"
                      ? <span title={b.error} className="text-loss">✗ failed</span>
                      : <span className="text-gain">{b.status}</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {b.status === "ok" && (
                      <>
                        <a className="text-copper-300 hover:text-copper-200 text-[12px] mr-4"
                           href={`/api/backups/${b.id}/download/`}>Download</a>
                        <button className="text-loss hover:underline text-[12px]"
                                onClick={() => setConfirm(b.id)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirm !== null && (
        <div role="dialog" aria-modal="true" aria-label="Confirm delete backup"
             className="fixed inset-0 bg-black/70 grid place-items-center z-50"
             onClick={() => setConfirm(null)}>
          <div className="ledger-surface p-5 w-96" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
            <p className="text-ink-200">Delete this backup? The file on disk will be removed.</p>
            <div className="flex justify-end gap-2 mt-4">
              <button className="ledger-ghost" onClick={() => setConfirm(null)}>Cancel</button>
              <button
                className="ledger-cta"
                style={{ background: "linear-gradient(180deg, var(--loss-400), var(--loss-500))", borderColor: "var(--loss-500)" }}
                onClick={() => {
                  del.mutate(confirm, {
                    onSuccess: () => push({ kind: "success", text: "Backup deleted." }),
                    onError: (e) => push({ kind: "error", text: (e as Error).message }),
                  });
                  setConfirm(null);
                }}
              >Delete</button>
            </div>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}
