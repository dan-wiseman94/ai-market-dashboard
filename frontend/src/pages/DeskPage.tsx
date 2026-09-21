import { useId, useState } from "react";
import { Link } from "react-router-dom";

import type { DeskEntry } from "@/api/desk";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useActDeskEntry, useDeskFeed, useDismissDeskEntry, useRunDeskSweep } from "@/hooks/useDesk";

/** Build the prefilled new-thesis deep-link query from an entry's open_thesis action. */
function openThesisQuery(entry: DeskEntry): string {
  const params = (entry.suggested_actions.find((a) => a.type === "open_thesis")?.params ?? {}) as Record<
    string,
    unknown
  >;
  return new URLSearchParams({
    ticker: String(params.ticker ?? entry.ticker ?? ""),
    direction: String(params.direction ?? "neutral"),
    rationale: String(params.rationale ?? ""),
  }).toString();
}

function subjectOf(entry: DeskEntry): string {
  return entry.ticker || "the book";
}

/** Convening runs a persona debate plus a synthesized verdict — several billed calls. */
function warRoomConfirm(entry: DeskEntry): string {
  return (
    `Convene the War Room on ${subjectOf(entry)}?\n\n` +
    "A debate is several billed model calls on your own API key — one per persona, plus " +
    "rebuttals and a synthesized verdict — and it runs on the worker as soon as you accept. " +
    "Spend is bounded by the monthly cost cap, not by this button."
  );
}

/** Revising re-reads the latest ready snapshot through the model to rewrite the house view. */
function reviseCoverageConfirm(entry: DeskEntry): string {
  return (
    `Revise the house view on ${subjectOf(entry)}?\n\n` +
    "This is one billed model call on your own API key, replaying the latest ready snapshot. " +
    "It rewrites the standing coverage note, and a material change is recorded as a revision."
  );
}

/**
 * The sweep control: a bare button here spends real money.
 *
 * Every candidate the sweep accepts opens a bounded autonomous investigation, so one
 * click is several billed model calls — the same shape as the eval-run control, so it
 * carries the same visible cost sentence and the same explicit gate before anything is
 * POSTed. The POST is fire-and-forget (the work is dispatched to the worker), so the
 * banner says "queued", never "done".
 */
function SweepControl() {
  const sweep = useRunDeskSweep();
  const [confirming, setConfirming] = useState(false);
  const [queued, setQueued] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const costId = useId();

  function submit() {
    setConfirming(false);
    setError(null);
    sweep.mutate(undefined, {
      onSuccess: () => setQueued(true),
      onError: (e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not queue the sweep."),
    });
  }

  return (
    <section data-testid="desk-sweep" className="mt-4 rounded border border-rule p-3">
      <p id={costId} className="text-sm text-ink/70">
        A sweep ranks the day's anomalies and opens a bounded autonomous investigation on each
        one it accepts — several billed model calls and tool round-trips per anomaly, on your own
        API key, and one sweep can accept several. Spend is bounded by the autonomous daily cap
        (AI_AUTONOMOUS_DAILY_CAP_USD) and the desk's own daily origination cap, not by this
        button.
      </p>
      <div className="mt-2">
        <button
          type="button"
          className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
          onClick={() => setConfirming(true)}
          disabled={confirming || sweep.isPending}
          aria-describedby={costId}
        >
          {sweep.isPending ? "Queuing…" : "Run sweep…"}
        </button>
      </div>

      {confirming && (
        <div data-testid="desk-sweep-confirm" className="mt-3 rounded border border-rule p-3 text-sm">
          <p className="text-ink/80">
            This costs real money. Each anomaly the sweep accepts is one autonomous
            investigation — several billed model calls — charged to your own API key. It cannot
            be undone or refunded once queued.
          </p>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded border border-rule px-3 py-1 text-ink/70 hover:text-ink"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              className="rounded border border-rule px-3 py-1 hover:bg-ink/5"
            >
              Yes, spend money and run it
            </button>
          </div>
        </div>
      )}

      {error && (
        <p data-testid="desk-sweep-error" role="alert" className="mt-2 text-sm text-loss">
          {error}
        </p>
      )}

      {queued && !error && (
        <p data-testid="desk-sweep-queued" role="status" className="mt-2 text-sm text-ink/60">
          Sweep queued — it runs on the worker, and findings appear in this list as each
          investigation finishes. Queued is not finished.
        </p>
      )}
    </section>
  );
}

export default function DeskPage() {
  const { data: entries = [], isLoading, refetch } = useDeskFeed();
  const act = useActDeskEntry();
  const dismiss = useDismissDeskEntry();

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">The Desk</h1>
      <p className="mt-1 text-sm text-ink/70">What the analyst flagged on its own — anomalies it investigated.</p>

      <SweepControl />

      {isLoading ? (
        <Skeleton where="desk" />
      ) : entries.length === 0 ? (
        <EmptyState title="Nothing flagged yet" body="The sweep has not surfaced any anomalies. Run a sweep or enable the scheduled sweep." />
      ) : (
        <ul className="mt-4 divide-y divide-rule">
          {entries.map((e) => (
            <li key={e.id} className="py-4">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{e.anomaly_type} · {e.ticker || "book"}</span>
                <span className="text-ink/50">{e.status}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <p className="text-sm text-ink/80">{e.finding}</p>
                {e.investigation_thread_id != null && (
                  <Link
                    to={`/threads/${e.investigation_thread_id}`}
                    className="shrink-0 text-xs text-ink/60 hover:text-ink/90 underline"
                  >
                    View investigation
                  </Link>
                )}
              </div>
              {e.status === "new" && (
                <>
                  <div className="mt-2 flex gap-2">
                    {e.suggested_actions.some((a) => a.type === "convene_warroom") && (
                      <button
                        className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                        aria-describedby={`desk-act-cost-${e.id}`}
                        onClick={async () => {
                          if (!window.confirm(warRoomConfirm(e))) return;
                          await act.mutateAsync({ id: e.id, action: "convene_warroom" });
                          refetch();
                        }}
                      >
                        {e.suggested_actions.find((a) => a.type === "convene_warroom")?.label ?? "Convene War Room"}
                      </button>
                    )}
                    {e.suggested_actions.some((a) => a.type === "revise_coverage") && (
                      <button
                        className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                        aria-describedby={`desk-act-cost-${e.id}`}
                        onClick={async () => {
                          if (!window.confirm(reviseCoverageConfirm(e))) return;
                          await act.mutateAsync({ id: e.id, action: "revise_coverage" });
                          refetch();
                        }}
                      >
                        {e.suggested_actions.find((a) => a.type === "revise_coverage")?.label ?? "Revise Coverage"}
                      </button>
                    )}
                    {e.suggested_actions.some((a) => a.type === "open_thesis") && (
                      <Link
                        to={`/theses/new?${openThesisQuery(e)}`}
                        className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                      >
                        {e.suggested_actions.find((a) => a.type === "open_thesis")?.label ?? "Open thesis"}
                      </Link>
                    )}
                    <button
                      className="rounded border border-rule px-2 py-1 text-xs text-ink/60 hover:bg-ink/5"
                      onClick={async () => { await dismiss.mutateAsync(e.id); refetch(); }}
                    >
                      Dismiss
                    </button>
                  </div>
                  {e.suggested_actions.some(
                    (a) => a.type === "convene_warroom" || a.type === "revise_coverage",
                  ) && (
                    <p id={`desk-act-cost-${e.id}`} className="mt-1 text-xs text-ink/50">
                      Convening and revising each run billed model calls on your own API key.
                      Opening a thesis and dismissing do not.
                    </p>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
