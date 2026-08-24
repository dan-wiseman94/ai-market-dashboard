import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchSnapshotDiff, fetchSnapshotTimeline } from "@/api/snapshots";
import { Skeleton } from "@/components/Skeleton";

/**
 * "What changed since your last look at $TICKER" — an on-demand, per-ticker
 * expander for the watchlist. Reuses the existing snapshot timeline + auto-
 * resolving diff endpoint: the latest ready snapshot for the ticker, diffed
 * against the prior one. Fetches only when expanded (no load-time request storm
 * across a whole watchlist).
 */
export function TickerChanges({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false);

  const timelineQ = useQuery({
    queryKey: ["snapshot-timeline", ticker],
    queryFn: () => fetchSnapshotTimeline(ticker),
    enabled: open,
  });
  const latest = timelineQ.data?.results?.[0];

  const diffQ = useQuery({
    queryKey: ["snapshot-diff", latest?.id],
    queryFn: () => fetchSnapshotDiff(latest!.id),
    enabled: open && !!latest,
    retry: false, // a 400 {no_prior} is expected, not worth retrying
  });

  return (
    <div className="border-b border-rule last:border-b-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between py-2 text-sm hover:text-copper-300"
      >
        <span className="font-medium text-ink-100">{ticker}</span>
        <span className="text-ink-400">{open ? "Hide" : "What changed?"}</span>
      </button>
      {open && (
        <div className="pb-3 text-sm" data-testid={`ticker-changes-${ticker}`}>
          {timelineQ.isLoading ? (
            <Skeleton where={`ticker-changes-${ticker}`} className="h-5 w-40" />
          ) : !latest ? (
            <span className="text-ink-500">No snapshots of {ticker} yet.</span>
          ) : diffQ.isLoading ? (
            <span className="text-ink-500">Computing diff…</span>
          ) : diffQ.isError ? (
            <span className="text-ink-500">
              {(diffQ.error as Error)?.message ?? "No prior snapshot to compare against."}
            </span>
          ) : (
            <div className="space-y-1">
              <p className="text-ink-400">
                Since your previous capture ·{" "}
                <Link
                  to={`/costs/snapshot/${latest.id}`}
                  className="text-copper-300 hover:underline"
                >
                  snapshot #{latest.id}
                </Link>
              </p>
              <pre className="whitespace-pre-wrap font-mono text-[12px] text-ink-300">
                {diffQ.data?.delta || "(no changes)"}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
