import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useThesis, useCloseThesis } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import { STATUS_BADGE, DIRECTION_LABEL } from "@/components/thesis/ThesisBadges";
import type { ThesisStatus } from "@/api/thesis";

const CLOSE_STATUSES: Array<{
  value: Exclude<ThesisStatus, "open">;
  label: string;
}> = [
  { value: "closed_win", label: "Closed — Win" },
  { value: "closed_loss", label: "Closed — Loss" },
  { value: "closed_scratch", label: "Closed — Scratch" },
  { value: "invalidated", label: "Invalidated" },
];

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="ledger-eyebrow mb-0.5">{label}</dt>
      <dd className="text-ink-100 text-[14px]">{children}</dd>
    </div>
  );
}

export default function ThesisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tid = id ? parseInt(id, 10) : null;
  const { data: thesis, isLoading } = useThesis(tid);
  const closeThesis = useCloseThesis();
  const { push } = useToast();

  const [showCloseForm, setShowCloseForm] = useState(false);
  const [closeStatus, setCloseStatus] =
    useState<Exclude<ThesisStatus, "open">>("closed_win");
  const [closeNote, setCloseNote] = useState("");

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!thesis) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <EmptyState title="Thesis not found" body="This thesis does not exist or has been deleted." />
      </div>
    );
  }

  const { label: statusLabel, className: statusClass } =
    STATUS_BADGE[thesis.status];

  const handleClose = (e: React.FormEvent) => {
    e.preventDefault();
    closeThesis.mutate(
      { id: thesis.id, body: { status: closeStatus, close_note: closeNote } },
      {
        onSuccess: () => {
          push({ kind: "success", text: "Thesis closed." });
          setShowCloseForm(false);
          setCloseNote("");
        },
        onError: (err) =>
          push({ kind: "error", text: (err as Error).message }),
      },
    );
  };

  return (
    <main className="max-w-3xl mx-auto p-6 ledger-fade-in">
      {/* Masthead */}
      <header className="mb-8 pb-6 border-b border-rule">
        <div className="flex items-center gap-3 mb-3">
          <span className="ledger-eyebrow">Thesis · #{thesis.id}</span>
          <span className="flex-1 h-px bg-rule-soft" />
          <Link
            to="/theses"
            className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors uppercase tracking-wider"
          >
            ← Theses
          </Link>
        </div>
        <div className="flex items-start gap-3">
          <h1
            className="ledger-display flex-1"
            style={{ fontSize: "clamp(1.4rem, 2.2vw, 1.8rem)" }}
          >
            {thesis.title}
          </h1>
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded text-[12px] font-mono font-medium shrink-0 mt-1 ${statusClass}`}
          >
            {statusLabel}
          </span>
        </div>
        <div className="flex items-center gap-3 mt-2">
          <span className="font-mono text-[13px] text-copper-400 uppercase tracking-wide">
            {thesis.ticker}
          </span>
          <span className="text-ink-500 font-mono text-[11px]">·</span>
          <span className="font-mono text-[13px] text-ink-300">
            {DIRECTION_LABEL[thesis.direction]}
          </span>
          <span className="text-ink-500 font-mono text-[11px]">·</span>
          <span
            className="font-mono text-[13px] text-copper-400"
            title="Conviction"
            aria-label={`Conviction ${thesis.conviction}`}
          >
            {"★".repeat(thesis.conviction)}
            {"☆".repeat(5 - thesis.conviction)}
          </span>
        </div>
      </header>

      {/* Core fields */}
      <dl className="grid grid-cols-2 gap-x-8 gap-y-5 mb-8">
        {thesis.rationale && (
          <div className="col-span-2">
            <Field label="Rationale">{thesis.rationale}</Field>
          </div>
        )}
        {thesis.entry_price && (
          <Field label="Entry price">${thesis.entry_price}</Field>
        )}
        {thesis.target_price && (
          <Field label="Target price">${thesis.target_price}</Field>
        )}
        {thesis.invalidation_price && (
          <Field label="Invalidation price">${thesis.invalidation_price}</Field>
        )}
        {thesis.horizon_days != null && (
          <Field label="Horizon">{thesis.horizon_days} days</Field>
        )}
        <Field label="Opened">
          {new Date(thesis.opened_at).toLocaleDateString()}
        </Field>
        {thesis.closed_at && (
          <Field label="Closed">
            {new Date(thesis.closed_at).toLocaleDateString()}
          </Field>
        )}
        {thesis.close_note && (
          <div className="col-span-2">
            <Field label="Close note">{thesis.close_note}</Field>
          </div>
        )}
      </dl>

      {/* Source links */}
      {(thesis.thread_id || thesis.snapshot_id) && (
        <section className="mb-8 ledger-surface px-5 py-4">
          <div className="ledger-eyebrow mb-3">Source</div>
          <div className="flex gap-4">
            {thesis.thread_id && (
              <Link
                to={`/threads/${thesis.thread_id}`}
                className="font-mono text-[12px] text-copper-400 hover:text-copper-300 transition-colors"
              >
                Thread #{thesis.thread_id} →
              </Link>
            )}
            {thesis.snapshot_id && (
              <span className="font-mono text-[12px] text-ink-400">
                Snapshot #{thesis.snapshot_id}
              </span>
            )}
            {thesis.review_thread_id && (
              <Link
                to={`/threads/${thesis.review_thread_id}`}
                className="font-mono text-[12px] text-ink-400 hover:text-copper-300 transition-colors"
              >
                Review thread #{thesis.review_thread_id} →
              </Link>
            )}
          </div>
        </section>
      )}

      {/* Close control — only shown when open */}
      {thesis.status === "open" && (
        <section className="mb-8">
          {!showCloseForm ? (
            <button
              className="ledger-ghost px-4 py-2 text-[13px]"
              onClick={() => setShowCloseForm(true)}
              data-testid="open-close-form-btn"
            >
              Close thesis…
            </button>
          ) : (
            <form
              onSubmit={handleClose}
              className="ledger-surface px-5 py-4 space-y-4"
              data-testid="close-thesis-form"
            >
              <div className="ledger-eyebrow mb-1">Close thesis</div>
              <div>
                <label
                  htmlFor="close-status"
                  className="block text-[12px] text-ink-400 mb-1"
                >
                  Outcome
                </label>
                <select
                  id="close-status"
                  value={closeStatus}
                  onChange={(e) =>
                    setCloseStatus(
                      e.target.value as Exclude<ThesisStatus, "open">,
                    )
                  }
                  className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
                >
                  {CLOSE_STATUSES.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="close-note"
                  className="block text-[12px] text-ink-400 mb-1"
                >
                  Note (optional)
                </label>
                <textarea
                  id="close-note"
                  value={closeNote}
                  onChange={(e) => setCloseNote(e.target.value)}
                  rows={3}
                  placeholder="What happened? What did you learn?"
                  className="bg-ink-void border border-rule rounded px-3 py-2 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 resize-none placeholder:text-ink-500"
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={closeThesis.isPending}
                  className="ledger-cta px-4 py-1.5 text-[13px]"
                >
                  {closeThesis.isPending ? "Saving…" : "Confirm close"}
                </button>
                <button
                  type="button"
                  className="ledger-ghost px-4 py-1.5 text-[13px]"
                  onClick={() => setShowCloseForm(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {/* Post-mortems placeholder — Phase 2 */}
      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="ledger-eyebrow">Post-mortems</h2>
          <span className="flex-1 h-px bg-rule" />
        </div>
        {/* Phase 2: post-mortem cards */}
        <EmptyState
          title="Post-mortems appear here"
          body="AI-assisted post-mortems will be available in a future update."
        />
      </section>
    </main>
  );
}
