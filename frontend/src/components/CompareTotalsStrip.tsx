import type { BranchState } from "@/hooks/useBranchState";

type Props = { state: Record<number, BranchState> };

export default function CompareTotalsStrip({ state }: Props) {
  const entries = Object.values(state);
  const withCost = entries.filter((b) => b.cost !== undefined);
  if (withCost.length === 0) return null;
  const total = withCost.reduce((acc, b) => acc + (b.cost ?? 0), 0);
  const slowestMs = Math.max(0, ...entries.map((b) => b.durationMs ?? 0));

  return (
    <div className="flex gap-4 px-3 py-1.5 text-xs text-slate-400 border-b border-slate-800">
      <span>Total: <span className="text-slate-200 font-mono">${total.toFixed(4)}</span></span>
      <span>{entries.length} branches</span>
      {slowestMs > 0 && <span>{(slowestMs / 1000).toFixed(1)}s slowest</span>}
    </div>
  );
}
