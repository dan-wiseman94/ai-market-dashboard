import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import type { DashboardBriefing } from "@/hooks/useDashboard";

const DATE_FMT = new Intl.DateTimeFormat([], {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function StatusBadge({ status }: { status: string }) {
  const classes =
    status === "ready"
      ? "text-gain-400 border-gain-400/30"
      : status === "running"
        ? "text-copper-300 border-copper-400/30"
        : status === "failed"
          ? "text-loss-400 border-loss-400/30"
          : "text-ink-400 border-ink-600";
  return (
    <span
      className={`font-mono text-[9px] uppercase tracking-loose2 border px-1.5 py-0.5 rounded-ledger ${classes}`}
    >
      {status}
    </span>
  );
}

export function BriefingSummaryTile({
  briefing,
}: {
  briefing: DashboardBriefing | null;
}) {
  return (
    <div className="ledger-surface overflow-hidden h-full">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Morning briefing</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/briefing"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          Open →
        </Link>
      </div>
      <div className="px-5 py-5">
        {briefing == null ? (
          <EmptyState title="No briefing yet" body="Run the first briefing." />
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <StatusBadge status={briefing.status} />
              <span className="font-mono text-[11px] text-ink-500">
                {briefing.scheduled_date ?? "—"}
              </span>
            </div>
            <div className="font-mono text-[11px] text-ink-500">
              {DATE_FMT.format(new Date(briefing.created_at))}
            </div>
            <Link
              to="/briefing"
              className="mt-2 inline-flex items-center gap-1 font-mono text-[11px] text-copper-300 hover:text-copper-200 transition-colors"
            >
              Read briefing →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
