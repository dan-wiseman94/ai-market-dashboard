import { useCallback } from "react";
import MarketContextStrip from "@/components/MarketContextStrip";
import PositionsTable from "@/components/PositionsTable";
import CostChip from "@/components/CostChip";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useMarketStatus } from "@/hooks/useMarketStatus";
import { sessionKind, type SessionKind } from "@/lib/marketSession";
import { useDashboard } from "@/hooks/useDashboard";
import { useChannel } from "@/hooks/useChannel";
import type { NotificationWsMsg } from "@/realtime/notificationEvents";
import { SkeletonRows } from "@/components/Skeleton";
import { OpenThesesTile } from "@/components/dashboard/OpenThesesTile";
import { ObserverTodayTile } from "@/components/dashboard/ObserverTodayTile";
import { ArmedTriggersTile } from "@/components/dashboard/ArmedTriggersTile";
import { BriefingSummaryTile } from "@/components/dashboard/BriefingSummaryTile";
import { UpcomingEventsRow } from "@/components/dashboard/UpcomingEventsRow";
import { PositionsBookTile } from "@/components/dashboard/PositionsBookTile";
import { DivergenceTile } from "@/components/dashboard/DivergenceTile";
import { BookTile } from "@/components/BookTile";
import { DeskTile } from "@/components/DeskTile";
import { RegimeTile } from "@/components/RegimeTile";

const DATE_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "long", month: "long", day: "numeric", year: "numeric",
});

// Hero session display, keyed off the authoritative backend phase (same source
// as the nav MarketStatusBadge — see @/lib/marketSession).
const SESSION: Record<SessionKind, { label: string; tone: string; dot: string }> = {
  open: { label: "NYSE Open", tone: "text-gain-400", dot: "var(--gain-400)" },
  extended: { label: "Extended Hours", tone: "text-copper-300", dot: "var(--copper-400)" },
  closed: { label: "Closed", tone: "text-ink-400", dot: "var(--ink-500)" },
};

const TAPE_VERB: Record<SessionKind, string> = {
  open: "open",
  extended: "in extended hours",
  closed: "closed",
};

function greetingForHour(hour: number): string {
  if (hour < 5) return "Late watch";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 21) return "Good evening";
  return "Late watch";
}

function SessionStatus({ kind }: { kind: SessionKind }) {
  const { label, tone, dot } = SESSION[kind];
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-loose2">
      <span className="relative inline-block h-1.5 w-1.5 rounded-full" style={{ background: dot }}>
        {kind === "open" && (
          <span
            aria-hidden
            className="absolute inset-0 rounded-full ledger-pulse"
            style={{ color: dot }}
          />
        )}
      </span>
      <span className={tone}>{label}</span>
    </span>
  );
}

function TilesLoading() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-6">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="ledger-surface p-5">
          <SkeletonRows rows={4} />
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const { data: marketData } = useMarketStatus();
  const equity = marketData?.markets?.us_equity;
  const kind: SessionKind = equity ? sessionKind(equity) : "closed";

  const { data: dashboard, isLoading: dashLoading } = useDashboard();

  // Live refresh: invalidate the dashboard query whenever an observer completion,
  // trigger firing, backup, or export event arrives over the notifications channel.
  const qc = useQueryClient();
  const dashboardLiveHandler = useCallback(
    (m: NotificationWsMsg) => {
      if (m.type === "notification.event") {
        qc.invalidateQueries({ queryKey: ["dashboard"] });
      }
    },
    [qc],
  );
  useChannel("notifications", dashboardLiveHandler);

  const now = new Date();
  const date = DATE_FMT.format(now);
  const greeting = greetingForHour(now.getHours());

  return (
    <main className="px-8 py-8 max-w-[1400px] mx-auto ledger-fade-in">
      <header className="mb-10 ledger-stagger">
        <div className="flex items-center gap-4 mb-4">
          <SessionStatus kind={kind} />
          <span className="h-px flex-1 bg-rule-soft" />
          <span className="font-mono text-[11px] text-ink-400 uppercase tracking-loose2">
            {date}
          </span>
        </div>

        <div className="flex items-end justify-between gap-8 flex-wrap">
          <div>
            <div className="ledger-eyebrow mb-3">Desk · today</div>
            <h1 className="ledger-display">
              {greeting}, <em>the tape</em> is {TAPE_VERB[kind]}.
            </h1>
            <p className="mt-3 max-w-xl text-ink-300 text-[14px] leading-relaxed">
              The market, your book, and what the machines have noticed since you last looked.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <CostChip />
            <Link to="/snapshot" className="ledger-cta">
              <span>Capture snapshot</span>
              <span aria-hidden className="font-mono text-[11px] opacity-70">⏎</span>
            </Link>
          </div>
        </div>
      </header>

      <section className="mb-10 ledger-reveal" style={{ animationDelay: "220ms" }}>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="ledger-eyebrow">Market context</h2>
          <Link to="/market/$SPX" className="font-mono text-[10px] text-ink-500 hover:text-copper-300 transition-colors uppercase tracking-wider">
            Tickers →
          </Link>
        </div>
        <MarketContextStrip />
      </section>

      <section className="mb-8 ledger-reveal" style={{ animationDelay: "300ms" }}>
        <h2 className="ledger-eyebrow mb-4">Command centre</h2>
        {dashLoading ? (
          <TilesLoading />
        ) : dashboard ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-6">
            <OpenThesesTile theses={dashboard.theses} />
            <RegimeTile regime={dashboard.regime} />
            <BookTile book={dashboard.book} />
            <DeskTile desk={dashboard.desk} />
            <DivergenceTile />
            <ObserverTodayTile observer={dashboard.observer} />
            <ArmedTriggersTile triggers={dashboard.triggers} />
            <BriefingSummaryTile briefing={dashboard.briefing} />
            <PositionsBookTile />
          </div>
        ) : null}
      </section>

      {dashboard && (
        <section className="mb-8 ledger-reveal" style={{ animationDelay: "360ms" }}>
          <UpcomingEventsRow events={dashboard.events} />
        </section>
      )}

      <div className="grid grid-cols-1 gap-8 ledger-reveal" style={{ animationDelay: "420ms" }}>
        <section>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="ledger-eyebrow">The book</h2>
            <Link to="/watchlists" className="font-mono text-[10px] text-ink-500 hover:text-copper-300 transition-colors uppercase tracking-wider">
              Watchlists →
            </Link>
          </div>
          <PositionsTable />
        </section>
      </div>

      <footer className="mt-16 pt-6 border-t border-rule-soft flex items-center gap-3 text-[11px] font-mono text-ink-500">
        <span className="text-copper-500/70" aria-hidden>◈</span>
        <span className="uppercase tracking-loose2">Ledger</span>
        <span className="text-ink-600">·</span>
        <span>observational only · no broker writes</span>
        <span className="flex-1" />
        <span>press <kbd className="ledger-kbd">?</kbd> for shortcuts</span>
      </footer>
    </main>
  );
}
