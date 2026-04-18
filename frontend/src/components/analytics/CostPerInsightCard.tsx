import { useCostPerInsight } from "@/hooks/useAnalytics";

export function CostPerInsightCard() {
  const { data, isLoading, error } = useCostPerInsight();
  return (
    <section className="ledger-surface p-5">
      <header className="ledger-eyebrow mb-3">Cost per insight (30d)</header>
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{String(error)}</p>}
      {data && (
        <dl className="grid grid-cols-2 gap-3 font-mono text-sm">
          <Row label="Total" value={`$${Number(data.total_cost_usd).toFixed(2)}`} />
          <Row label="Threads" value={data.threads_with_ai} />
          <Row label="Snapshots" value={data.snapshots_with_ai} />
          <Row label="Trigger fires" value={data.trigger_fires} />
          <Row label="Insights" value={data.insights} />
          <Row
            label="CPI"
            value={
              data.cost_per_insight_usd
                ? `$${Number(data.cost_per_insight_usd).toFixed(4)}`
                : "—"
            }
          />
        </dl>
      )}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between border-b border-slate-800 py-1">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-slate-100">{value}</dd>
    </div>
  );
}
