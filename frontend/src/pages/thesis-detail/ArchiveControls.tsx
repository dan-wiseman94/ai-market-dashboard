import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useArchiveThesis, usePurgeThesis, useRestoreThesis } from "@/hooks/useTheses";
import { useToast } from "@/hooks/useToast";
import type { Thesis } from "@/api/thesis";

/**
 * Archive / restore, plus the separated permanent delete.
 *
 * Archiving is the ordinary exit: the thesis leaves the list and its price
 * guard is disarmed, but every post-mortem it feeds — and so the conviction
 * calibration, Brier score and cohort base rates computed from them — survives.
 * Purging is kept behind its own disclosure because it cannot be undone, and
 * the backend refuses it outright (409) once a post-mortem has completed.
 */
export function ArchiveControls({ thesis }: { thesis: Thesis }) {
  const navigate = useNavigate();
  const { push } = useToast();
  const archive = useArchiveThesis();
  const restore = useRestoreThesis();
  const purge = usePurgeThesis();
  const [showPurge, setShowPurge] = useState(false);
  const [purgeError, setPurgeError] = useState<string | null>(null);
  const purgeHelpId = useId();
  const archived = thesis.archived_at !== null;

  const onArchive = () =>
    archive.mutate(thesis.id, {
      onSuccess: () =>
        push({ kind: "success", text: "Archived. Post-mortems and calibration are kept." }),
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });

  const onRestore = () =>
    restore.mutate(thesis.id, {
      onSuccess: () =>
        push({ kind: "success", text: "Restored. The price guard stays off — re-arm it below." }),
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });

  const onPurge = () => {
    if (
      !window.confirm(
        `Permanently delete "${thesis.title}"? This cannot be undone and removes the thesis, its journal links and its review thread reference.`,
      )
    ) {
      return;
    }
    setPurgeError(null);
    purge.mutate(thesis.id, {
      onSuccess: () => {
        push({ kind: "success", text: "Thesis deleted." });
        navigate("/theses");
      },
      onError: (e) =>
        setPurgeError(
          e instanceof ApiError ? e.message : "Could not delete this thesis — please try again.",
        ),
    });
  };

  return (
    <section className="mb-8 pb-6 border-b border-rule" data-testid="archive-controls">
      <h2 className="ledger-eyebrow mb-3">Lifecycle</h2>

      {archived ? (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="text-sm text-ink-300">
            This thesis is archived — it is hidden from the Theses list and its price guard is
            off.
          </p>
          <button
            type="button"
            onClick={onRestore}
            disabled={restore.isPending}
            className="rounded border border-copper-600 px-3 py-1 text-[12px] text-copper-200 transition-colors hover:bg-copper-900/30 disabled:opacity-50"
          >
            {restore.isPending ? "Restoring…" : "Restore thesis"}
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onArchive}
            disabled={archive.isPending}
            className="rounded border border-rule px-3 py-1 text-[12px] text-ink-300 transition-colors hover:border-rule-soft hover:text-copper-300 disabled:opacity-50"
          >
            {archive.isPending ? "Archiving…" : "Archive thesis"}
          </button>
          <p className="text-[11px] text-ink-500">
            Hides it from the list and disarms the price guard. Post-mortems, lessons and
            calibration are kept, and you can restore it at any time.
          </p>
        </div>
      )}

      <div className="mt-4 rounded border border-loss-500/40 bg-loss-500/[0.04] p-3">
        <button
          type="button"
          onClick={() => setShowPurge((v) => !v)}
          aria-expanded={showPurge}
          aria-controls={purgeHelpId}
          className="font-mono text-[11px] uppercase tracking-wider text-loss-400 hover:text-loss-300"
        >
          {showPurge ? "▾" : "▸"} Delete permanently
        </button>
        <div id={purgeHelpId} hidden={!showPurge} className="mt-3 space-y-3">
          <p className="text-[11px] leading-relaxed text-ink-400">
            Deleting drops the row outright — there is no undo, and it is refused while a
            completed post-mortem exists, because that post-mortem feeds your conviction
            calibration and cohort base rates. Archive instead unless this thesis was entered by
            mistake.
          </p>
          {purgeError && (
            <p role="alert" className="text-sm text-loss-400">
              {purgeError}
            </p>
          )}
          <button
            type="button"
            onClick={onPurge}
            disabled={purge.isPending}
            data-testid="purge-thesis-btn"
            className="rounded border border-loss-500 px-3 py-1 text-[12px] text-loss-400 transition-colors hover:bg-loss-500/10 disabled:opacity-50"
          >
            {purge.isPending ? "Deleting…" : "Delete this thesis permanently"}
          </button>
        </div>
      </div>
    </section>
  );
}
