import { usePositions } from "@/hooks/usePositions";
import type { Position } from "@/api/market";
import { SkeletonRows } from "@/components/Skeleton";
import { fmt, plClass, signed } from "@/utils/format";

export default function PositionsTable() {
  const { data, isLoading, error } = usePositions();

  if (error) {
    return (
      <div className="ledger-surface px-5 py-4 text-loss font-mono text-[12px]">
        Could not load positions: {(error as Error).message}
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className="ledger-surface px-5 py-4">
        <SkeletonRows rows={4} />
      </div>
    );
  }
  if (!data?.length) {
    return (
      <div className="ledger-surface px-5 py-6 text-center">
        <div className="font-display italic text-ink-300 text-lg">Flat.</div>
        <div className="font-mono text-[11px] text-ink-500 mt-1">No open positions.</div>
      </div>
    );
  }

  const totalPl = data.reduce((s: number, p: Position) => s + (p.unrealized_pl ?? 0), 0);
  const totalDay = data.reduce((s: number, p: Position) => s + (p.day_pl ?? 0), 0);

  return (
    <div className="ledger-surface overflow-hidden">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-rule">
            <th className="text-left font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-5 py-3">Ticker</th>
            <th className="text-right font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-3 py-3">Qty</th>
            <th className="text-right font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-3 py-3">Avg</th>
            <th className="text-right font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-3 py-3">Mkt Value</th>
            <th className="text-right font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-3 py-3">Day P/L</th>
            <th className="text-right font-mono text-[10px] uppercase tracking-loose2 text-ink-400 px-5 py-3">Unrealized</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p: Position, idx: number) => {
            const day = p.day_pl ?? 0;
            const unrl = p.unrealized_pl ?? 0;
            return (
              <tr
                key={p.ticker}
                className={[
                  "group transition-colors duration-150 hover:bg-copper-500/[0.04]",
                  idx > 0 ? "border-t border-rule-soft" : "",
                ].join(" ")}
              >
                <td className="px-5 py-3">
                  <span className="font-display text-[15px] font-medium text-ink-50 tracking-tight">
                    {p.ticker}
                  </span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums font-mono text-ink-200">
                  {p.qty.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right tabular-nums font-mono text-ink-300">
                  {fmt(p.avg_cost)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums font-mono text-ink-100">
                  {fmt(p.mkt_value)}
                </td>
                <td className={`px-3 py-3 text-right tabular-nums font-mono ${plClass(day)}`}>
                  {signed(day)}
                </td>
                <td className={`px-5 py-3 text-right tabular-nums font-mono ${plClass(unrl)}`}>
                  {signed(unrl)}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t border-rule-strong bg-ink-void/30">
            <td className="px-5 py-3 font-mono text-[10px] uppercase tracking-loose2 text-copper-400" colSpan={4}>
              Book totals
            </td>
            <td className={`px-3 py-3 text-right font-mono tabular-nums font-semibold ${plClass(totalDay)}`}>
              {signed(totalDay)}
            </td>
            <td className={`px-5 py-3 text-right font-mono tabular-nums font-semibold ${plClass(totalPl)}`}>
              {signed(totalPl)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
