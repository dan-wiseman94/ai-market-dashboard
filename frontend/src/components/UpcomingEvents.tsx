import { Link } from "react-router-dom";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";

export default function UpcomingEvents({ tickers = [] }: { tickers?: string[] }) {
  const { data } = useUpcomingEvents(tickers, 7);
  const items = [...(data?.earnings ?? []), ...(data?.macro ?? [])]
    .sort((a, b) => a.days_until - b.days_until)
    .slice(0, 2);
  if (items.length === 0) return null;
  return (
    <div className="flex items-center gap-2 text-sm">
      {items.map((e) => (
        <Link
          key={`${e.kind}-${e.ticker}-${e.event_time}`}
          to="/events"
          className="rounded border border-rule px-2 py-1 font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          {e.ticker ? `${e.ticker} earnings` : e.title} · {e.days_until}d
        </Link>
      ))}
    </div>
  );
}
