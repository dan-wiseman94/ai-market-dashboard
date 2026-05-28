import { useObserverTimeline } from "@/hooks/useAnalytics";
import { AnalyticsCard } from "./AnalyticsCard";

// Stacked-bar segments, in DOM order (flex-col-reverse renders them bottom→top).
const SEGMENTS = [
  { key: "success", className: "bg-emerald-700" },
  { key: "skipped", className: "bg-amber-700" },
  { key: "failed", className: "bg-rose-700" },
] as const;

export function ObserverTimelineCard() {
  const q = useObserverTimeline();
  return (
    <AnalyticsCard testid="analytics-card-timeline" title="Observer runs (30d)" query={q} wide>
      {(data) => {
        const days = data.days ?? [];
        const max = Math.max(
          1,
          ...days.map((d) => d.success + d.failed + d.skipped),
        );
        return (
          <>
            <ul className="flex items-end gap-1 h-32">
              {days.map((d) => (
                <li key={d.date} className="flex-1 flex flex-col-reverse" title={d.date}>
                  {SEGMENTS.map((s) => (
                    <span
                      key={s.key}
                      className={s.className}
                      style={{ height: `${(d[s.key] / max) * 100}%` }}
                    />
                  ))}
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
