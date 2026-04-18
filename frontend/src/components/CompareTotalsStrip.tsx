import type { BranchState } from "@/hooks/useBranchState";
import { usd } from "@/utils/format";

type Props = { state: Record<number, BranchState> };

export default function CompareTotalsStrip({ state }: Props) {
  const entries = Object.values(state);
  const withCost = entries.filter((b) => b.cost !== undefined);
  if (withCost.length === 0) return null;
  const total = withCost.reduce((acc, b) => acc + (b.cost ?? 0), 0);
  const slowestMs = Math.max(0, ...entries.map((b) => b.durationMs ?? 0));

  return (
    <div className="flex items-center gap-5 px-4 py-2 text-[11px] border-b border-rule bg-ink-void/30 font-mono">
      <span className="inline-flex items-center gap-2 text-ink-400">
        <span className="ledger-eyebrow">Total</span>
        <span className="text-ink-100 tabular-nums">{usd(total)}</span>
      </span>
      <span className="h-3 w-px bg-rule" />
      <span className="text-ink-400 tabular-nums">{`${entries.length} branches`}</span>
      {slowestMs > 0 && (
        <>
          <span className="h-3 w-px bg-rule" />
          <span className="text-ink-400 tabular-nums">{`${(slowestMs / 1000).toFixed(1)}s slowest`}</span>
        </>
      )}
    </div>
  );
}
