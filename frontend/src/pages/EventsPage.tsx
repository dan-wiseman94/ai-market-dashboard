import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";
import { useWatchlists } from "@/hooks/useWatchlists";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import type { MarketEvent } from "@/api/market";

function EventRow({ e }: { e: MarketEvent }) {
  const eps = (e.detail as { eps_est?: number } | null)?.eps_est;
  return (
    <li className="flex items-baseline justify-between border-b border-rule py-2">
      <span className="font-medium">
        {e.ticker ? `${e.ticker} earnings` : e.title}
        {e.when_hint ? ` (${e.when_hint.toUpperCase()})` : ""}
      </span>
      <span className="text-sm text-muted">
        in {e.days_until}d{eps != null ? ` · est EPS ${eps}` : ""}
      </span>
    </li>
  );
}

export default function EventsPage() {
  const { data: watchlists } = useWatchlists();
  const tickers = (watchlists ?? []).flatMap((w) =>
    w.symbols.map((s) => s.ticker),
  );
  const { data, isLoading } = useUpcomingEvents(tickers, 30);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <SkeletonRows rows={5} />
      </div>
    );
  }

  const earnings = data?.earnings ?? [];
  const macro = data?.macro ?? [];

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-8 ledger-fade-in">
      <header className="pb-6 border-b border-rule">
        <span className="ledger-eyebrow">Events</span>
        <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
          Market Calendar
        </h1>
      </header>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Upcoming earnings</h2>
        {earnings.length === 0 ? (
          <EmptyState
            title="No upcoming earnings"
            body="Across your watchlists in the next 30 days."
          />
        ) : (
          <ul>
            {earnings.map((e) => (
              <EventRow key={`${e.ticker}-${e.event_time}`} e={e} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Macro calendar</h2>
        {macro.length === 0 ? (
          <EmptyState
            title="No macro events"
            body="No high-impact US events in the next 30 days."
          />
        ) : (
          <ul>
            {macro.map((m) => (
              <EventRow key={`${m.kind}-${m.event_time}`} e={m} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
