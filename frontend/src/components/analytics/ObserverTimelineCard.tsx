import { useObserverTimeline } from "@/hooks/useAnalytics";

export function ObserverTimelineCard() {
  const { data, isLoading, error } = useObserverTimeline();
  const max = Math.max(
    1,
    ...(data?.days.map((d) => d.success + d.failed + d.skipped) ?? [1]),
  );
  return (
    <section data-testid="analytics-card-timeline" className="ledger-surface p-5 md:col-span-2">
      <header className="ledger-eyebrow mb-3">Observer runs (30d)</header>
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{String(error)}</p>}
      {data && (
        <ul className="flex items-end gap-1 h-32">
          {data.days.map((d) => (
            <li key={d.date} className="flex-1 flex flex-col-reverse" title={d.date}>
              <span
                className="bg-emerald-700"
                style={{ height: `${(d.success / max) * 100}%` }}
              />
              <span
                className="bg-amber-700"
                style={{ height: `${(d.skipped / max) * 100}%` }}
              />
              <span
                className="bg-rose-700"
                style={{ height: `${(d.failed / max) * 100}%` }}
              />
              <span className="sr-only">{d.date}</span>
            </li>
          ))}
        </ul>
      )}
      {data && (
        <div className="flex gap-4 mt-2 text-xs text-slate-500 font-mono">
          <span>▓ success</span>
          <span>▒ skipped</span>
          <span>░ failed</span>
        </div>
      )}
    </section>
  );
}
