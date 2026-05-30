import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import type { DashboardEvents, DashboardEvent } from "@/hooks/useDashboard";

function EventChip({ event }: { event: DashboardEvent }) {
  const label = event.ticker
    ? `${event.ticker} ${event.kind === "earnings" ? "earnings" : event.title}`
    : event.title;
  const impactClass =
    event.impact === "high"
      ? "text-loss-400 border-loss-400/30"
      : "text-ink-400 border-ink-600";
  return (
    <Link
      to="/events"
      className={`flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-[11px] hover:border-copper-500/60 hover:text-copper-300 transition-colors ${impactClass}`}
    >
      <span>{label}</span>
      <span className="text-ink-600">·</span>
      <span className="text-ink-500">{event.days_until}d</span>
      {event.when_hint && (
        <span className="text-ink-600 uppercase text-[9px]">
          {event.when_hint}
        </span>
      )}
    </Link>
  );
}

export function UpcomingEventsRow({ events }: { events: DashboardEvents }) {
  const all = [...events.earnings, ...events.macro]
    .sort((a, b) => a.days_until - b.days_until)
    .slice(0, 8);

  return (
    <div className="ledger-surface overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Upcoming events · 7 days</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/events"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          Calendar →
        </Link>
      </div>
      <div className="px-5 py-4">
        {all.length === 0 ? (
          <EmptyState title="No events in the next 7 days" />
        ) : (
          <div className="flex flex-wrap gap-2">
            {all.map((e) => (
              <EventChip key={`${e.kind}-${e.ticker}-${e.event_time}`} event={e} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
