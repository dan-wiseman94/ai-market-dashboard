import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useCurrentRegime, useRefreshRegime, useRegimeHistory } from "@/hooks/useRegime";

const COMPOSITE_TONE: Record<string, string> = {
  "Risk-On": "text-emerald-600",
  "Neutral-Transitional": "text-ink",
  "Risk-Off": "text-copper",
  Stress: "text-red-600",
};

function RefreshRegimeButton() {
  const refresh = useRefreshRegime();
  return (
    <button
      type="button"
      disabled={refresh.isPending}
      className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
      onClick={() => refresh.mutate()}
    >
      {refresh.isPending ? "Refreshing…" : "Refresh"}
    </button>
  );
}

export default function RegimePage() {
  const { data: current, isLoading } = useCurrentRegime();
  const { data: history = [] } = useRegimeHistory();

  if (isLoading) return <Skeleton where="regime-page" />;
  if (!current) {
    return (
      <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
        <EmptyState
          title="No regime reading yet"
          body="The regime engine has not produced a reading. Refresh it now or wait for the next scheduled run."
        />
        <div className="mt-4">
          <RefreshRegimeButton />
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Market regime</h1>
        <RefreshRegimeButton />
      </div>
      <p className={`mt-2 text-3xl font-bold ${COMPOSITE_TONE[current.composite] ?? "text-ink"}`}>
        {current.composite}
      </p>
      {current.narrative && <p className="mt-2 text-ink/80">{current.narrative}</p>}

      <h2 className="mt-6 text-lg font-medium">Axes</h2>
      <dl className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-5">
        {Object.entries(current.axes).map(([axis, label]) => (
          <div key={axis} className="rounded border border-rule p-3">
            <dt className="text-xs uppercase tracking-wide text-ink/60">{axis}</dt>
            <dd className="mt-1 font-medium">{label}</dd>
          </div>
        ))}
      </dl>

      <h2 className="mt-6 text-lg font-medium">Drivers</h2>
      <ul className="mt-2 list-disc pl-5">
        {current.drivers.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>

      <h2 className="mt-6 text-lg font-medium">History</h2>
      <ul className="mt-2 divide-y divide-rule">
        {history.map((r) => (
          <li key={r.id} className="flex justify-between py-2 text-sm">
            <span>{new Date(r.created_at).toLocaleString()}</span>
            <span className={COMPOSITE_TONE[r.composite] ?? "text-ink"}>{r.composite}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
