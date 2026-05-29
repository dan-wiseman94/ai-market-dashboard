import { useQuery } from "@tanstack/react-query";
import { fetchSnapshotTimeline, explainDiff, type SnapshotListRow } from "@/api/snapshots";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/useToast";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";

type Props = { ticker: string };

function DeltaBadge({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="text-ink-500 text-xs">—</span>;
  const sign = pct >= 0 ? "+" : "";
  const color = pct >= 0 ? "text-emerald-400" : "text-rose-400";
  return (
    <span className={`font-mono text-xs ${color}`}>
      {sign}{pct.toFixed(2)}%
    </span>
  );
}

export default function TickerTimeline({ ticker }: Props) {
  const navigate = useNavigate();
  const { push } = useToast();
  const [explaining, setExplaining] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["snapshot-timeline", ticker],
    queryFn: () => fetchSnapshotTimeline(ticker),
    enabled: ticker.length > 0,
  });

  if (!ticker) {
    return (
      <EmptyState
        title="Enter a ticker to view timeline"
        body="Type a ticker symbol in the filter above."
      />
    );
  }

  if (isLoading) return <SkeletonRows rows={4} />;

  const rows: SnapshotListRow[] = data?.results ?? [];

  if (rows.length === 0) {
    return (
      <EmptyState
        title={`No snapshots for ${ticker}`}
        body="Capture a snapshot with this ticker to start building a timeline."
      />
    );
  }

  async function handleExplain(row: SnapshotListRow) {
    setExplaining(row.id);
    try {
      const res = await explainDiff(row.id);
      navigate(`/threads/${res.thread_id}`);
    } catch (err) {
      push({ kind: "error", text: (err as Error).message ?? "Could not explain diff" });
    } finally {
      setExplaining(null);
    }
  }

  return (
    <div className="relative">
      <div className="absolute left-4 top-3 bottom-3 w-px bg-rule" aria-hidden />
      <ul className="space-y-4 pl-10">
        {rows.map((row) => (
          <li key={row.id} className="relative">
            <span
              className="absolute -left-6 top-2 w-2.5 h-2.5 rounded-full border-2 border-copper-500 bg-ink-900"
              aria-hidden
            />
            <div className="p-3 rounded border border-rule hover:border-copper-700/50 transition-colors">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-ink-500">
                    {new Date(row.captured_at).toLocaleString()}
                  </span>
                  <span className="text-ink-500 text-xs">
                    ({formatDistanceToNow(new Date(row.captured_at))} ago)
                  </span>
                </div>
                <DeltaBadge pct={row.headline_delta_pct} />
              </div>
              {row.objective && (
                <p className="mt-1 text-sm text-ink-200 truncate">{row.objective}</p>
              )}
              <div className="mt-2 flex items-center gap-2">
                <span className="font-mono text-xs text-ink-500">
                  {row.section_kinds.join(", ") || "—"}
                </span>
                {row.headline_delta_pct != null && (
                  <button
                    type="button"
                    disabled={explaining === row.id}
                    onClick={() => handleExplain(row)}
                    className="ml-auto px-2 py-0.5 text-xs rounded border border-copper-700 text-copper-300 hover:bg-copper-900/30 disabled:opacity-50 transition-colors"
                  >
                    {explaining === row.id ? "…" : "✦ explain"}
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
