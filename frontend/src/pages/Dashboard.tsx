import MarketContextStrip from "@/components/MarketContextStrip";
import PositionsTable from "@/components/PositionsTable";
import CostChip from "@/components/CostChip";
import RecentTriggersCard from "@/components/RecentTriggersCard";
import { Link } from "react-router-dom";

const ET_HOUR_FMT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric", minute: "2-digit", hour12: false,
});
const DATE_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "long", month: "long", day: "numeric", year: "numeric",
});

function SessionStatus() {
  const now = new Date();
  const [h] = ET_HOUR_FMT.format(now).split(":").map(Number);
  const day = now.getUTCDay();
  const weekday = day >= 1 && day <= 5;
  const open = weekday && h >= 9 && h < 16; // rough — backend is authoritative
  const preOrPost = weekday && ((h >= 4 && h < 9) || (h >= 16 && h < 20));
  const label = open ? "NYSE Open" : preOrPost ? "Extended Hours" : "Closed";
  const tone = open ? "text-gain" : preOrPost ? "text-copper-300" : "text-ink-400";
  const dot = open ? "var(--gain-400)" : preOrPost ? "var(--copper-400)" : "var(--ink-500)";
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-loose2">
      <span className="relative inline-block h-1.5 w-1.5 rounded-full" style={{ background: dot }}>
        {open && (
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

export default function Dashboard() {
  const now = new Date();
  const date = DATE_FMT.format(now);
  const hour = now.getHours();
  const greeting =
    hour < 5 ? "Late watch" :
    hour < 12 ? "Good morning" :
    hour < 17 ? "Good afternoon" :
    hour < 21 ? "Good evening" : "Late watch";

  return (
    <main className="px-8 py-8 max-w-[1400px] mx-auto ledger-fade-in">
      {/* Editorial hero */}
      <header className="mb-10 ledger-stagger">
        <div className="flex items-center gap-4 mb-4">
          <SessionStatus />
          <span className="h-px flex-1 bg-rule-soft" />
          <span className="font-mono text-[11px] text-ink-400 uppercase tracking-loose2">
            {date}
          </span>
        </div>

        <div className="flex items-end justify-between gap-8 flex-wrap">
          <div>
            <div className="ledger-eyebrow mb-3">Desk · today</div>
            <h1 className="ledger-display">
              {greeting}, <em>the tape</em> is open.
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

      {/* Market context */}
      <section className="mb-10 ledger-reveal" style={{ animationDelay: "220ms" }}>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="ledger-eyebrow">Market context</h2>
          <Link to="/market/SPY" className="font-mono text-[10px] text-ink-500 hover:text-copper-300 transition-colors uppercase tracking-wider">
            Tickers →
          </Link>
        </div>
        <MarketContextStrip />
      </section>

      {/* Two-column: positions + recent triggers */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        <section className="lg:col-span-3 ledger-reveal" style={{ animationDelay: "300ms" }}>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="ledger-eyebrow">The book</h2>
            <Link to="/watchlists" className="font-mono text-[10px] text-ink-500 hover:text-copper-300 transition-colors uppercase tracking-wider">
              Watchlists →
            </Link>
          </div>
          <PositionsTable />
        </section>

        <section className="lg:col-span-2 ledger-reveal" style={{ animationDelay: "380ms" }}>
          <RecentTriggersCard />
        </section>
      </div>

      {/* Footer signature */}
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
