import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useActDeskEntry, useDeskFeed, useDismissDeskEntry, useRunDeskSweep } from "@/hooks/useDesk";

export default function DeskPage() {
  const { data: entries = [], isLoading, refetch } = useDeskFeed();
  const sweep = useRunDeskSweep();
  const act = useActDeskEntry();
  const dismiss = useDismissDeskEntry();

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">The Desk</h1>
        <button
          className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
          onClick={async () => { await sweep.mutateAsync(); refetch(); }}
          disabled={sweep.isPending}
        >
          {sweep.isPending ? "Sweeping…" : "Run sweep"}
        </button>
      </div>
      <p className="mt-1 text-sm text-ink/70">What the analyst flagged on its own — anomalies it investigated.</p>

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
                <div className="mt-2 flex gap-2">
                  {e.suggested_actions.some((a) => a.type === "convene_warroom") && (
                    <button
                      className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                      onClick={async () => { await act.mutateAsync({ id: e.id, action: "convene_warroom" }); refetch(); }}
                    >
                      {e.suggested_actions.find((a) => a.type === "convene_warroom")?.label ?? "Convene War Room"}
                    </button>
                  )}
                  {e.suggested_actions.some((a) => a.type === "revise_coverage") && (
                    <button
                      className="rounded border border-rule px-2 py-1 text-xs hover:bg-ink/5"
                      onClick={async () => { await act.mutateAsync({ id: e.id, action: "revise_coverage" }); refetch(); }}
                    >
                      {e.suggested_actions.find((a) => a.type === "revise_coverage")?.label ?? "Revise Coverage"}
                    </button>
                  )}
                  <button
                    className="rounded border border-rule px-2 py-1 text-xs text-ink/60 hover:bg-ink/5"
                    onClick={async () => { await dismiss.mutateAsync(e.id); refetch(); }}
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
