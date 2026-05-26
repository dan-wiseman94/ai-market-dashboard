import { useLeaderboard } from "@/hooks/useAnalytics";
import { AnalyticsCard } from "./AnalyticsCard";

export function ProviderLeaderboardCard() {
  const q = useLeaderboard();
  return (
    <AnalyticsCard testid="analytics-card-leaderboard" title="Provider leaderboard (30d)" query={q}>
      {(data) => (
        <>
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-slate-400 text-left">
                <th>Model</th><th>Runs</th><th>Cost</th>
                <th>Fwd %</th><th>Cov</th>
              </tr>
            </thead>
            <tbody>
              {(data.rows ?? []).map((r) => (
                <tr
                  key={`${r.provider}:${r.model}`}
                  className="border-t border-slate-800"
                >
                  <td className="py-1">{r.model}</td>
                  <td>{r.runs}</td>
                  <td>${Number(r.total_cost_usd).toFixed(2)}</td>
                  <td>
                    {r.avg_forward_return_pct == null
                      ? "—"
                      : r.avg_forward_return_pct.toFixed(2)}
                  </td>
                  <td>{r.coverage_pct.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-slate-500">
            Fwd % = return over 1 trading session on each ticker's calendar. Cov = coverage:
            share of runs with a real price bar at both endpoints (gaps shown as —).
          </p>
        </>
      )}
    </AnalyticsCard>
  );
}
