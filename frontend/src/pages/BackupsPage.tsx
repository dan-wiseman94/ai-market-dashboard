import { useState } from "react";
import { Link } from "react-router-dom";
import { useBackups, useDeleteBackup, useRestoreBackup, useRunBackupNow } from "@/hooks/useBackups";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import SettingsSection from "@/components/settings/SettingsSection";
import { fmtSize } from "@/utils/format";
import { RestoreFailure, type Backup, type RestoreResponse } from "@/api/backups";

// Every documented refusal, spelled out as what the operator should do next. The
// server's own `detail` is rendered underneath — this is the guidance, not a
// replacement for it. Codes come from apps/backups/views.py::restore.
const RESTORE_GUIDANCE: Record<string, string> = {
  restore_disabled: "Restore from the UI is switched off. Turn on “Allow restore from the UI” under Backup restore in System settings, then try again.",
  confirmation_mismatch: "The confirmation text did not match the filename exactly. Nothing was touched.",
  backup_not_restorable: "This backup is not in an “ok” state, so it cannot be restored. Pick a completed backup.",
  backup_in_progress: "A backup or another restore is already running. Wait for it to finish, then try again — nothing was touched.",
  backup_file_missing: "The archive is gone from disk, so there was nothing to restore. The database was not touched; delete this row and use another backup.",
  restore_failed: "pg_restore failed part-way. The database may be partially restored — check it before using the app, and consider re-running the restore or falling back to `make restore` on the host.",
  restore_timeout: "pg_restore ran past its 1800s limit and was killed. The database may be partially restored — check the server before using the app.",
  restore_no_response: "The server never answered. The restore may still be running: wait a minute, reload, and check the data before trusting it.",
  restore_unreadable: "The restore returned something this page could not read. Reload and check the data before trusting it.",
};

const FALLBACK_GUIDANCE = "The restore did not complete. Check the database before using the app.";

function RestoreErrorPanel({ error }: { error: RestoreFailure }) {
  const { code, detail, expected, exit_code, stderr } = error.body;
  return (
    <div role="alert" className="mt-4 rounded border border-loss-500/40 bg-loss-500/10 p-3 text-[12px]">
      <p className="font-medium text-loss-400">{RESTORE_GUIDANCE[code] ?? FALLBACK_GUIDANCE}</p>
      <p className="mt-1.5 text-ink-300">{detail}</p>
      {code === "restore_disabled" && (
        <p className="mt-1.5">
          <Link to="/settings/system" className="text-copper-300 hover:text-copper-200 underline">
            Open System settings → Backup restore
          </Link>
        </p>
      )}
      {expected !== undefined && (
        <p className="mt-1.5 text-ink-400">
          Expected: <code className="font-mono text-ink-200">{expected}</code>
        </p>
      )}
      {exit_code !== undefined && (
        <p className="mt-1.5 text-ink-400">pg_restore exit code {exit_code}</p>
      )}
      {stderr !== undefined && stderr !== "" && (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 font-mono text-[11px] text-ink-300">
          {stderr}
        </pre>
      )}
      <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-500">
        {code} · HTTP {error.status === 0 ? "—" : error.status}
      </p>
    </div>
  );
}

function RestoreDialog({
  backup,
  pending,
  error,
  onCancel,
  onRestore,
}: {
  backup: Backup;
  pending: boolean;
  error: RestoreFailure | null;
  onCancel: () => void;
  onRestore: (confirm: string) => void;
}) {
  const [typed, setTyped] = useState("");
  // Deliberate friction: the API is AllowAny on loopback and this overwrites the
  // live database, so only the exact filename arms the button.
  const armed = typed === backup.filename;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="restore-dialog-title"
      className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4"
    >
      <div className="ledger-surface w-[36rem] max-w-full p-5" tabIndex={-1}>
        <h2 id="restore-dialog-title" className="font-display text-[1.05rem] text-loss">
          Restore the database from this backup?
        </h2>
        <p className="mt-2 text-[13px] text-ink-200">
          This replaces the <strong>entire live database</strong> with the contents of this
          archive. Every thread, thesis, snapshot and setting recorded since it was taken is
          dropped. There is no undo.
        </p>
        <p className="mt-2 text-[12px] text-ink-400">
          The restore runs synchronously and usually takes a few seconds. This page stays locked
          until it answers.
        </p>

        <fieldset disabled={pending} className="mt-4 border-0 p-0">
          <legend className="text-[12px] text-ink-300">Confirm by typing the filename</legend>
          <p id="restore-confirm-help" className="mt-1 text-[11px] text-ink-500">
            Type <code className="font-mono text-ink-200">{backup.filename}</code> exactly to
            enable the Restore button.
          </p>
          <label htmlFor="restore-confirm" className="sr-only">
            Backup filename
          </label>
          <input
            id="restore-confirm"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-describedby="restore-confirm-help"
            className="ledger-input mt-2 w-full py-2 font-mono text-[12px]"
          />
        </fieldset>

        {pending && (
          <p role="status" className="mt-4 text-[12px] text-ink-200" aria-live="polite">
            Restoring the database from {backup.filename}… do not reload or navigate away.
          </p>
        )}
        {error && <RestoreErrorPanel error={error} />}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="ledger-ghost" disabled={pending} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="ledger-cta disabled:opacity-40"
            disabled={!armed || pending}
            aria-busy={pending}
            style={{
              background: "linear-gradient(180deg, var(--loss-400), var(--loss-500))",
              borderColor: "var(--loss-500)",
            }}
            onClick={() => onRestore(typed)}
          >
            {pending ? "Restoring…" : "Restore"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DeleteDialog({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm delete backup"
      className="fixed inset-0 bg-black/70 grid place-items-center z-50"
      onClick={onCancel}
    >
      <div className="ledger-surface p-5 w-96" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <p className="text-ink-200">Delete this backup? The file on disk will be removed.</p>
        <div className="flex justify-end gap-2 mt-4">
          <button className="ledger-ghost" onClick={onCancel}>Cancel</button>
          <button
            className="ledger-cta"
            style={{ background: "linear-gradient(180deg, var(--loss-400), var(--loss-500))", borderColor: "var(--loss-500)" }}
            onClick={onConfirm}
          >Delete</button>
        </div>
      </div>
    </div>
  );
}

function BackupRowActions({
  backup,
  busy,
  onDelete,
  onRestore,
}: {
  backup: Backup;
  busy: boolean;
  onDelete: () => void;
  onRestore: () => void;
}) {
  if (backup.status !== "ok") return null;
  return (
    <>
      <a
        className={`text-copper-300 hover:text-copper-200 text-[12px] mr-4 ${busy ? "pointer-events-none opacity-40" : ""}`}
        href={`/api/backups/${backup.id}/download/`}
        aria-disabled={busy || undefined}
        tabIndex={busy ? -1 : undefined}
      >Download</a>
      <button
        type="button"
        className="text-copper-300 hover:text-copper-200 text-[12px] mr-4 disabled:opacity-40"
        disabled={busy}
        onClick={onRestore}
      >Restore</button>
      <button
        type="button"
        className="text-loss hover:underline text-[12px] disabled:opacity-40"
        disabled={busy}
        onClick={onDelete}
      >Delete</button>
    </>
  );
}

function BackupTable({
  rows,
  busy,
  onDelete,
  onRestore,
}: {
  rows: Backup[];
  busy: boolean;
  onDelete: (id: number) => void;
  onRestore: (b: Backup) => void;
}) {
  return (
    <div className="ledger-surface overflow-hidden">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-rule text-left">
            {["Created", "Filename", "Size", "Kind", "Status", "Actions"].map((h) => (
              <th
                key={h}
                className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-copper-400"
              >
                {h === "Actions" ? <span className="sr-only">Actions</span> : h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-rule-soft">
          {rows.map((b) => (
            <tr key={b.id} data-testid={`backup-row-${b.id}`} className={b.status !== "ok" ? "opacity-60" : ""}>
              <td className="px-4 py-2.5 text-ink-300">{new Date(b.created_at).toLocaleString()}</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-ink-200">{b.filename}</td>
              <td className="px-4 py-2.5 tabular-nums text-ink-200">{fmtSize(b.size_bytes)}</td>
              <td className="px-4 py-2.5">
                <span className="ledger-pill">{b.kind}</span>
              </td>
              <td className="px-4 py-2.5">
                {b.status === "failed" ? (
                  <span className="text-loss">✗ failed{b.error ? ` — ${b.error}` : ""}</span>
                ) : (
                  <span className="text-gain">{b.status}</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-right whitespace-nowrap">
                <BackupRowActions
                  backup={b}
                  busy={busy}
                  onDelete={() => onDelete(b.id)}
                  onRestore={() => onRestore(b)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RestoredBanner({ result }: { result: RestoreResponse }) {
  return (
    <div role="status" className="rounded border border-gain-500/40 bg-gain-500/10 p-3 text-[12px]">
      <p className="font-medium text-gain-300">
        Restored from <span className="font-mono">{result.filename}</span> in{" "}
        {(result.duration_ms / 1000).toFixed(1)}s.
      </p>
      <p className="mt-1.5 text-ink-200">
        Everything on screen has been reloaded and now shows the restored data. Anything you were
        looking at before this point is gone.
      </p>
      {!result.workers_quiesced && <p className="mt-1.5 text-ink-400">{result.warning}</p>}
    </div>
  );
}

export default function BackupsPage() {
  const { data = [], isLoading } = useBackups();
  const { push } = useToast();
  const run = useRunBackupNow();
  const del = useDeleteBackup();
  const restore = useRestoreBackup();
  const [confirm, setConfirm] = useState<number | null>(null);
  const [target, setTarget] = useState<Backup | null>(null);
  const [restored, setRestored] = useState<RestoreResponse | null>(null);

  const restoring = restore.isPending;
  // Only a RestoreFailure carries the documented envelope; anything else is a
  // programming error and surfaces through the toast instead.
  const restoreError = restore.error instanceof RestoreFailure ? restore.error : null;

  const openRestore = (b: Backup) => {
    restore.reset();
    setRestored(null);
    setTarget(b);
  };

  const submitRestore = (typed: string) => {
    if (!target) return;
    restore.mutate(
      { id: target.id, confirm: typed },
      {
        onSuccess: (res) => {
          setTarget(null);
          setRestored(res);
          push({ kind: "success", text: "Database restored — every view now shows restored data." });
        },
        // The dialog stays open on failure so the panel can explain the code and
        // the user can correct the confirmation or retry.
        onError: (e) => push({ kind: "error", text: e.message }),
      },
    );
  };

  return (
    <SettingsSection
      title="Backups"
      description="Daily at 02:30 UTC · keep last 7 scheduled."
      action={
        <button
          className="ledger-cta disabled:opacity-50"
          disabled={run.isPending || restoring}
          onClick={() => run.mutate(undefined, {
            onSuccess: () => push({ kind: "info", text: "Backup queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {run.isPending ? "Queuing…" : "Back up now"}
        </button>
      }
    >
      {restored && <RestoredBanner result={restored} />}
      {isLoading && <SkeletonRows rows={4} />}
      {!isLoading && data.length === 0 && (
        <EmptyState title="No backups yet" body="The nightly job will create one at 02:30 UTC." />
      )}

      {data.length > 0 && (
        <BackupTable
          rows={data}
          busy={restoring}
          onDelete={setConfirm}
          onRestore={openRestore}
        />
      )}

      {confirm !== null && (
        <DeleteDialog
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            del.mutate(confirm, {
              onSuccess: () => push({ kind: "success", text: "Backup deleted." }),
              onError: (e) => push({ kind: "error", text: (e as Error).message }),
            });
            setConfirm(null);
          }}
        />
      )}

      {target && (
        <RestoreDialog
          backup={target}
          pending={restoring}
          error={restoreError}
          onCancel={() => { setTarget(null); restore.reset(); }}
          onRestore={submitRestore}
        />
      )}
    </SettingsSection>
  );
}
