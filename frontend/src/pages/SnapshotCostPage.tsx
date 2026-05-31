import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useCostsSnapshot } from "@/hooks/useCosts";
import { fetchSnapshotDiff } from "@/api/snapshots";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

export default function SnapshotCostPage() {
  const { id } = useParams();
  const snapId = id ? Number(id) : null;
  const { data, isLoading } = useCostsSnapshot(snapId);
  const [showDiff, setShowDiff] = useState(false);

  const diffQ = useQuery({
    queryKey: ["snapshot-diff", snapId],
    queryFn: () => fetchSnapshotDiff(snapId!),
    enabled: showDiff && snapId !== null,
    retry: false,
  });

  if (isLoading) {
    return (
      <main className="p-6 max-w-2xl mx-auto space-y-4">
        <SkeletonRows rows={5} />
      </main>
    );
  }
  if (!data || data.length === 0) {
    return (
      <main className="p-6 max-w-2xl mx-auto">
        <EmptyState title={`No data for snapshot ${id}`} body="This snapshot hasn't been consumed by an AI run yet." />
      </main>
    );
  }

  return (
    <main className="p-6 max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-semibold">Snapshot {id} — cost attribution</h1>
      <table className="w-full text-sm border border-rule rounded">
        <thead className="bg-ink-900">
          <tr className="text-ink-400 text-left">
            <th className="py-1.5 px-2">Section</th>
            <th className="py-1.5 px-2">Tokens</th>
            <th className="py-1.5 px-2">Cost share</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.section} className="border-t border-rule">
              <td className="py-1.5 px-2">{r.section}</td>
              <td className="py-1.5 px-2 tabular-nums">{r.payload_tokens.toLocaleString()}</td>
              <td className="py-1.5 px-2 font-mono">${Number(r.cost_share_usd).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-500">Attribution is proportional to the section's share of payload tokens.</p>

      <section className="border-t border-rule pt-4 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-ink-200">Diff vs previous capture</h2>
          <button
            type="button"
            onClick={() => setShowDiff((v) => !v)}
            className="px-2 py-1 text-xs rounded bg-ink-800 hover:bg-ink-700"
          >{showDiff ? "Hide" : "Show diff"}</button>
        </div>
        {showDiff && (
          <>
            {diffQ.isLoading && <div className="text-xs text-ink-500">Computing diff…</div>}
            {diffQ.isError && (
              <div className="text-xs text-loss-400">
                {(diffQ.error as Error)?.message ?? "No prior snapshot to diff against"}
              </div>
            )}
            {diffQ.data && (
              <pre className="text-xs bg-ink-850 border border-rule rounded p-3 whitespace-pre-wrap">
                {diffQ.data.delta || "(no changes)"}
              </pre>
            )}
          </>
        )}
      </section>
    </main>
  );
}
