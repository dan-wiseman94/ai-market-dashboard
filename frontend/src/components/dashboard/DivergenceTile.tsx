import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { useDivergences } from "@/hooks/usePredictions";

/**
 * Open theses that conflict with the AI's current live call (rollup) —
 * a proactive risk surface so you don't have to open each thesis to check whether
 * the AI now disagrees. Fetches its own data; highest-conviction first.
 */
export function DivergenceTile() {
  const { data } = useDivergences();
  const rows = data?.rows ?? [];
  return (
    <div className="ledger-surface overflow-hidden h-full" data-testid="divergence-tile">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">AI divergences</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <span className="font-mono text-[11px] text-ink-400">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <div className="px-5 py-6">
          <EmptyState
            title="No divergences"
            body="The AI's current calls align with your open theses."
          />
        </div>
      ) : (
        <ul className="divide-y divide-rule-soft">
          {rows.slice(0, 6).map((r) => (
            <li
              key={r.thesis_id}
              className="flex items-center gap-3 px-5 py-3 hover:bg-copper-500/[0.04] transition-colors"
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/theses/${r.thesis_id}`}
                  className="font-mono text-[13px] text-ink-100 hover:text-copper-300 transition-colors font-medium"
                >
                  {r.ticker}
                </Link>
                <div className="font-mono text-[11px] text-ink-500 mt-0.5">
                  you {r.thesis_direction} · AI {r.ai_direction}
                </div>
              </div>
              <span
                className={`font-mono text-[9px] uppercase tracking-loose2 border px-1 py-0.5 rounded-ledger ${
                  r.agreement === "diverge"
                    ? "text-loss-400 border-loss-400/30"
                    : "text-ink-400 border-ink-600"
                }`}
              >
                {r.agreement}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
