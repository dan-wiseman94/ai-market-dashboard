import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { usePortfolioPositions } from "@/hooks/usePortfolio";
import type { PortfolioPosition } from "@/api/portfolio";

/** Sum unrealized P&L across a list of open positions. Decimals come as strings. */
function sumUnrealizedPnl(positions: PortfolioPosition[]): number {
  let total = 0;
  for (const p of positions) {
    const pnl = p.unrealized?.unrealized_pnl;
    if (pnl != null) total += pnl;
  }
  return total;
}

function pnlColor(pnl: number): string {
  if (pnl > 0) return "text-gain-400";
  if (pnl < 0) return "text-loss-400";
  return "text-ink-400";
}

function PositionRow({ position }: { position: PortfolioPosition }) {
  const pnl = position.unrealized?.unrealized_pnl ?? null;
  const pct = position.unrealized?.unrealized_pct ?? null;
  return (
    <li className="flex items-center gap-3 px-5 py-3 hover:bg-copper-500/[0.04] transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-mono text-[13px] text-ink-100 font-medium">
            {position.ticker}
          </span>
          <span
            className={`font-mono text-[9px] uppercase tracking-loose2 border px-1 py-0.5 rounded-ledger ${
              position.direction === "long"
                ? "text-gain-400 border-gain-400/30"
                : "text-loss-400 border-loss-400/30"
            }`}
          >
            {position.direction}
          </span>
        </div>
        <div className="font-mono text-[11px] text-ink-500">
          qty {Number(position.quantity).toLocaleString()} · cost{" "}
          {Number(position.avg_cost).toFixed(2)}
        </div>
      </div>
      <div className="text-right shrink-0">
        {pnl != null ? (
          <>
            <span
              data-testid={`tile-pnl-${position.id}`}
              className={`font-mono text-[12px] tabular-nums ${pnlColor(pnl)}`}
            >
              {pnl >= 0 ? "+" : ""}
              {pnl.toFixed(2)}
            </span>
            {pct != null && (
              <div
                className={`font-mono text-[9px] mt-0.5 ${pnlColor(pnl)}`}
              >
                {pct >= 0 ? "+" : ""}
                {pct.toFixed(1)}%
              </div>
            )}
          </>
        ) : (
          <span className="font-mono text-[12px] text-ink-600">—</span>
        )}
      </div>
    </li>
  );
}

export function PositionsBookTile() {
  const { data: positions } = usePortfolioPositions({ status: "open" });
  const openPositions = positions ?? [];
  const total = sumUnrealizedPnl(openPositions);
  const hasPositions = openPositions.length > 0;
  const anyPnlData = openPositions.some((p) => p.unrealized?.unrealized_pnl != null);

  return (
    <div className="ledger-surface overflow-hidden h-full">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">The book</span>
        <span className="flex-1 h-px bg-rule-soft" />
        {hasPositions && anyPnlData && (
          <span
            data-testid="tile-total-pnl"
            className={`font-mono text-[11px] tabular-nums ${pnlColor(total)}`}
          >
            {total >= 0 ? "+" : ""}
            {total.toFixed(2)}
          </span>
        )}
        <Link
          to="/portfolio"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          All →
        </Link>
      </div>
      {!hasPositions ? (
        <div className="px-5 py-6">
          <EmptyState
            title="No open positions"
            body="Track your book by adding a position."
          />
        </div>
      ) : (
        <ul className="divide-y divide-rule-soft">
          {openPositions.slice(0, 6).map((p) => (
            <PositionRow key={p.id} position={p} />
          ))}
        </ul>
      )}
    </div>
  );
}
