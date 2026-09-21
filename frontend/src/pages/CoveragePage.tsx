import { Link, useParams } from "react-router-dom";

import { ConveneWarRoomButton } from "@/components/ConveneWarRoomButton";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  type CoverageRevision,
  useCoverage,
  useReviseCoverage,
} from "@/hooks/useCoverage";
import { useToast } from "@/hooks/useToast";
import { convictionLabel, STANCE_LABEL, STANCE_TONE } from "@/lib/coverageStance";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Compact prior→new transition for a revision row; null when nothing structural moved. */
function transition(rev: CoverageRevision): string | null {
  const parts: string[] = [];
  const { stance: ps, conviction: pc } = rev.prior;
  const { stance: ns, conviction: nc } = rev.new;
  if (ns != null && ps !== ns) parts.push(`${ps ?? "—"} → ${ns}`);
  if (nc != null && pc !== nc) parts.push(`conviction ${pc ?? "—"} → ${nc}`);
  return parts.length ? parts.join(", ") : null;
}

export default function CoveragePage() {
  const { ticker = "" } = useParams();
  const { data: note, isLoading, isError } = useCoverage(ticker);
  const { push } = useToast();
  const revise = useReviseCoverage(ticker);

  function onRevise() {
    revise.mutate(undefined, {
      onSuccess: (res) =>
        push({
          kind: res.revised ? "success" : "info",
          text: res.revised
            ? "House view revised."
            : "Reaffirmed — nothing material changed, so no revision was written.",
        }),
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });
  }

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 ledger-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-100">{ticker}</h1>
          <p className="mt-1 text-sm text-ink-400 max-w-xl">
            The house view — a standing research note the desk revises with a
            reason, not one it re-derives from scratch each snapshot.
          </p>
          <Link
            to="/coverage"
            className="mt-2 inline-block text-xs text-ink-500 hover:text-copper-300"
          >
            ← All coverage
          </Link>
        </div>
        <div className="flex shrink-0 gap-2">
          {note && (
            <ConveneWarRoomButton
              subject={{ coverage_note_id: note.id }}
              className="rounded border border-rule px-3 py-1 text-sm text-ink-300 transition-colors hover:text-copper-300 disabled:opacity-50"
            />
          )}
          <button
            onClick={onRevise}
            disabled={revise.isPending}
            className="rounded border border-rule px-3 py-1 text-sm text-ink-300 transition-colors hover:text-copper-300 disabled:opacity-50"
          >
            {revise.isPending ? "Revising…" : "Revise now"}
          </button>
        </div>
      </div>

      {isLoading ? (
        <SkeletonRows rows={6} />
      ) : isError || !note ? (
        <EmptyState
          title={`No coverage yet for ${ticker}`}
          body={
            `Nothing has opened a house view on ${ticker} yet. An observer fire opens one ` +
            "automatically off a snapshot's primary ticker; to start it by hand, capture a " +
            "snapshot for this ticker and then “Revise now”."
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <button
                onClick={onRevise}
                disabled={revise.isPending}
                className="rounded border border-rule px-3 py-1 text-sm text-ink-300 transition-colors hover:text-copper-300 disabled:opacity-50"
              >
                {revise.isPending ? "Opening…" : "Open the house view"}
              </button>
              <Link
                to="/coverage"
                className="rounded border border-rule px-3 py-1 text-sm text-ink-400 transition-colors hover:text-copper-300"
              >
                All coverage
              </Link>
            </div>
          }
        />
      ) : (
        <>
          <section className="flex flex-wrap items-baseline gap-4">
            <span className={`text-lg font-semibold ${STANCE_TONE[note.stance]}`}>
              {STANCE_LABEL[note.stance]}
            </span>
            <span className="text-sm text-ink-400">
              conviction {convictionLabel(note.conviction)}
            </span>
            <span className="text-xs text-ink-500">
              updated {fmtDate(note.updated_at)}
            </span>
          </section>

          <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
                Bull case
              </h2>
              <p className="whitespace-pre-line text-sm text-ink-200">
                {note.bull_case || "—"}
              </p>
            </div>
            <div className="space-y-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
                Bear case
              </h2>
              <p className="whitespace-pre-line text-sm text-ink-200">
                {note.bear_case || "—"}
              </p>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Key levels
            </h2>
            {Object.keys(note.key_levels ?? {}).length ? (
              <div className="flex flex-wrap gap-2">
                {Object.entries(note.key_levels).map(([label, price]) => (
                  <span
                    key={label}
                    className="rounded border border-rule px-2 py-1 text-sm text-ink-300"
                  >
                    {label}:{" "}
                    <span className="text-copper-200">{String(price)}</span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-500">None noted.</p>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Watching for
            </h2>
            <p className="whitespace-pre-line text-sm text-ink-200">
              {note.watching_for || "—"}
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Revision history
            </h2>
            {note.revisions.length ? (
              <ol className="space-y-3">
                {note.revisions.map((rev) => {
                  const t = transition(rev);
                  return (
                    <li key={rev.id} className="border-l-2 border-rule pl-3">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="text-xs text-ink-500">
                          {fmtDate(rev.created_at)}
                        </span>
                        {t && <span className="text-xs text-copper-300">{t}</span>}
                      </div>
                      <p className="text-sm text-ink-200">{rev.reason}</p>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <EmptyState
                title="No revisions yet"
                body="This view hasn’t been revised since it was established."
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
