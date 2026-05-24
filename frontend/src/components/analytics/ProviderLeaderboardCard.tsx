import { useLeaderboard } from "@/hooks/useAnalytics";

export function ProviderLeaderboardCard() {
  const { data, isLoading, error } = useLeaderboard();
  return (
    <section data-testid="analytics-card-leaderboard" className="ledger-surface p-5">
      <header className="ledger-eyebrow mb-3">Provider leaderboard (30d)</header>
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{String(error)}</p>}
      {data && (
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
      )}
    </section>
  );
}
