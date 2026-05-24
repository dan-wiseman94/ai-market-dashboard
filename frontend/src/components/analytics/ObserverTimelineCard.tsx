import { useObserverTimeline } from "@/hooks/useAnalytics";
import { AnalyticsCard } from "./AnalyticsCard";

export function ObserverTimelineCard() {
  const q = useObserverTimeline();
  return (
    <AnalyticsCard testid="analytics-card-timeline" title="Observer runs (30d)" query={q} wide>
      {(data) => {
        const max = Math.max(
          1,
          ...(data.days ?? []).map((d) => d.success + d.failed + d.skipped),
        );
        return (
          <>
            <ul className="flex items-end gap-1 h-32">
              {(data.days ?? []).map((d) => (
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
            <div className="flex gap-4 mt-2 text-xs text-slate-500 font-mono">
              <span>▓ success</span>
              <span>▒ skipped</span>
              <span>░ failed</span>
            </div>
          </>
        );
      }}
    </AnalyticsCard>
  );
}
