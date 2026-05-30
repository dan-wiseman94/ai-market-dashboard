import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import type { DashboardThesis } from "@/hooks/useDashboard";

function pctColor(pct: number | null): string {
  if (pct == null) return "text-ink-400";
  return pct >= 0 ? "text-gain-400" : "text-loss-400";
}

function DirectionBadge({ direction }: { direction: string }) {
  const classes =
    direction === "bullish"
      ? "text-gain-400 border-gain-400/30"
      : direction === "bearish"
        ? "text-loss-400 border-loss-400/30"
        : "text-ink-400 border-ink-600";
  return (
    <span
      className={`font-mono text-[9px] uppercase tracking-loose2 border px-1 py-0.5 rounded-ledger ${classes}`}
    >
      {direction}
    </span>
  );
}

function ThesisRow({ thesis }: { thesis: DashboardThesis }) {
  const pct = thesis.pct_to_target;
  return (
    <li className="flex items-center gap-3 px-5 py-3 hover:bg-copper-500/[0.04] transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <Link
            to="/theses"
            className="font-mono text-[13px] text-ink-100 hover:text-copper-300 transition-colors font-medium"
          >
            {thesis.ticker}
          </Link>
          <DirectionBadge direction={thesis.direction} />
          <span className="font-mono text-[9px] text-ink-500">
            c{thesis.conviction}
          </span>
        </div>
        {thesis.current != null && (
          <div className="font-mono text-[11px] text-ink-500">
            {thesis.current.toFixed(2)}
          </div>
        )}
      </div>
      <div className="text-right shrink-0">
        {pct != null ? (
          <span className={`font-mono text-[12px] tabular-nums ${pctColor(pct)}`}>
            {pct >= 0 ? "+" : ""}
            {pct.toFixed(1)}%
          </span>
        ) : (
          <span className="font-mono text-[12px] text-ink-600">—</span>
        )}
        <div className="font-mono text-[9px] text-ink-600 mt-0.5">to target</div>
      </div>
    </li>
  );
}

export function OpenThesesTile({ theses }: { theses: DashboardThesis[] }) {
  return (
    <div className="ledger-surface overflow-hidden h-full">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Open theses</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/theses"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          All →
        </Link>
      </div>
      {theses.length === 0 ? (
        <div className="px-5 py-6">
          <EmptyState title="No open theses" body="Start a thesis from a thread." />
        </div>
      ) : (
        <ul className="divide-y divide-rule-soft">
          {theses.slice(0, 6).map((t) => (
            <ThesisRow key={t.id} thesis={t} />
          ))}
        </ul>
      )}
    </div>
  );
}
