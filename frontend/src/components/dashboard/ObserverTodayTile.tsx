import { Link } from "react-router-dom";
import type { DashboardObserver } from "@/hooks/useDashboard";

export function ObserverTodayTile({
  observer,
}: {
  observer: DashboardObserver;
}) {
  return (
    <div className="ledger-surface overflow-hidden h-full">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Observer</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/schedules"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          Schedules →
        </Link>
      </div>
      <div className="px-5 py-5 flex flex-col gap-4">
        <div className="flex items-end gap-3">
          <span
            className="font-display text-[2.5rem] leading-none tabular-nums text-ink-100"
            data-testid="observer-runs-today"
          >
            {observer.runs_today}
          </span>
          <span className="font-mono text-[11px] text-ink-400 mb-1.5">
            runs today
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-[15px] tabular-nums text-copper-300"
            data-testid="observer-enabled-schedules"
          >
            {observer.enabled_schedules}
          </span>
          <span className="font-mono text-[11px] text-ink-500">
            schedules armed
          </span>
        </div>
        <Link
          to="/threads/observer/1"
          className="mt-1 font-mono text-[11px] text-ink-500 hover:text-copper-300 transition-colors"
        >
          View timeline →
        </Link>
      </div>
    </div>
  );
}
