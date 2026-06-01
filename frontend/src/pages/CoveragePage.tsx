import { useParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  type CoverageRevision,
  type Stance,
  useCoverage,
  useReviseCoverage,
} from "@/hooks/useCoverage";

const STANCE_LABEL: Record<Stance, string> = {
  bull: "Bullish",
  bear: "Bearish",
  neutral: "Neutral",
};

const STANCE_TONE: Record<Stance, string> = {
  bull: "text-copper-300",
  bear: "text-ink-200",
  neutral: "text-ink-400",
};

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
  const revise = useReviseCoverage(ticker);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 ledger-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-100">{ticker}</h1>
          <p className="mt-1 text-sm text-ink-400 max-w-xl">
            The house view — a standing research note the desk revises with a
            reason, not one it re-derives from scratch each snapshot.
          </p>
        </div>
        <button
          onClick={() => revise.mutate()}
          disabled={revise.isPending}
          className="shrink-0 rounded border border-rule px-3 py-1 text-sm text-ink-300 transition-colors hover:text-copper-300 disabled:opacity-50"
        >
          {revise.isPending ? "Revising…" : "Revise now"}
        </button>
      </div>

      {isLoading ? (
        <SkeletonRows rows={6} />
      ) : isError || !note ? (
        <EmptyState
          title={`No coverage yet for ${ticker}`}
          body="Capture a snapshot for this ticker, then “Revise now” to establish the house view. Observer fires keep it current after that."
        />
      ) : (
        <>
          <section className="flex flex-wrap items-baseline gap-4">
            <span className={`text-lg font-semibold ${STANCE_TONE[note.stance]}`}>
              {STANCE_LABEL[note.stance]}
            </span>
            <span className="text-sm text-ink-400">
              conviction {note.conviction}/5
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
