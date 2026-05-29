import { useQuery } from "@tanstack/react-query";
import { fetchSnapshotDiff, explainDiff } from "@/api/snapshots";
import { SkeletonRows } from "@/components/Skeleton";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/useToast";
import { useState } from "react";

type Props = {
  ids: [number, number];
  onClose: () => void;
};

export default function CompareDrawer({ ids, onClose }: Props) {
  const navigate = useNavigate();
  const { push } = useToast();
  const [explaining, setExplaining] = useState(false);

  const [prevId, currId] = ids[0] < ids[1] ? ids : [ids[1], ids[0]];

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["snapshot-diff", prevId, currId],
    queryFn: () => fetchSnapshotDiff(currId, prevId),
  });

  async function handleExplain() {
    setExplaining(true);
    try {
      const res = await explainDiff(currId, prevId);
      navigate(`/threads/${res.thread_id}`);
    } catch (err) {
      push({ kind: "error", text: (err as Error).message ?? "Could not explain diff" });
    } finally {
      setExplaining(false);
    }
  }

  return (
    <div
      className="fixed inset-y-0 right-0 w-full max-w-xl z-40 flex flex-col border-l border-rule bg-ink-950/95 backdrop-blur"
      role="dialog"
      aria-label="Compare snapshots"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-rule">
        <div>
          <span className="ledger-eyebrow">Compare</span>
          <h2 className="text-sm font-medium text-ink-100">
            #{prevId} → #{currId}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close compare drawer"
          className="text-ink-400 hover:text-ink-100 transition-colors text-lg leading-none"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {isLoading && <SkeletonRows rows={6} />}
        {isError && (
          <p className="text-sm text-rose-400">
            {(error as Error)?.message ?? "Could not load diff"}
          </p>
        )}
        {data && (
          <pre className="text-xs bg-ink-950 border border-rule rounded p-3 whitespace-pre-wrap text-ink-200 leading-relaxed">
            {data.delta || "(no changes detected)"}
          </pre>
        )}
      </div>

      {data && (
        <div className="px-5 py-4 border-t border-rule">
          <button
            type="button"
            disabled={explaining}
            onClick={handleExplain}
            className="w-full px-4 py-2 rounded border border-copper-600 text-copper-200 hover:bg-copper-900/30 disabled:opacity-50 transition-colors text-sm font-medium"
          >
            {explaining ? "Submitting…" : "✦ explain with AI"}
          </button>
        </div>
      )}
    </div>
  );
}
