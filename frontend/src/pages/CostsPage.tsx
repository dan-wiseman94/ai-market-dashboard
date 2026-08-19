import { useState } from "react";
import CostCapBars from "@/components/costs/CostCapBars";
import DateRangePicker, { type Range } from "@/components/costs/DateRangePicker";
import DailyCostChart from "@/components/costs/DailyCostChart";
import BreakdownTables from "@/components/costs/BreakdownTables";
import { useCostsSummary, useCostsCaps, useCostsToday } from "@/hooks/useCosts";

function defaultRange(): Range {
  const now = new Date();
  const start = new Date(now.getTime() - 30 * 86400000);
  return { from: start.toISOString(), to: now.toISOString() };
}

function StatTile({
  label, value, sublabel,
}: { label: string; value: string; sublabel?: string }) {
  return (
    <div className="ledger-surface px-5 py-4 flex-1 min-w-[140px]">
      <div className="ledger-eyebrow mb-1.5">{label}</div>
      <div className="font-display text-[1.75rem] leading-none text-ink-50 tabular-nums"
           style={{ fontVariationSettings: '"opsz" 72, "SOFT" 60' }}>
        {value}
      </div>
      {sublabel && (
        <div className="font-mono text-[10px] text-ink-500 uppercase tracking-wider mt-2">
          {sublabel}
        </div>
      )}
    </div>
  );
}

export default function CostsPage() {
  const [range, setRange] = useState<Range>(defaultRange);
  const summary = useCostsSummary(range);
  const capsQ = useCostsCaps();
  const today = useCostsToday();

  const csvHref = `/api/costs/export.csv?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`;

  const totalInRange = Number(summary.data?.total ?? 0);
  const runsInRange =
    summary.data?.by_provider.reduce((s, p) => s + p.runs, 0) ?? 0;
  const daysInRange = summary.data?.daily.length ?? 0;
  const todayTotal = Number(today.data?.total_usd ?? "0");

  return (
    <main className="px-8 py-8 max-w-[1400px] mx-auto ledger-fade-in">
      <header className="mb-8 pb-6 border-b border-rule">
        <div className="flex items-center gap-4 mb-3">
          <span className="ledger-eyebrow">Ledger · Costs</span>
          <span className="flex-1 h-px bg-rule-soft" />
          <a
            href={csvHref}
            className="ledger-ghost py-1.5 text-[11px] font-mono uppercase tracking-wider"
          >
            ↓ Export CSV
          </a>
        </div>
        <div className="flex items-end justify-between gap-8 flex-wrap">
          <div>
            <h1 className="ledger-display" style={{ fontSize: "clamp(1.5rem, 2.6vw, 2.25rem)" }}>
              What <em className="italic text-copper-300">the machines</em> cost you.
            </h1>
            <p className="mt-2 text-ink-300 text-[14px] leading-relaxed max-w-xl">
              Every token, every call, every branch — tallied honestly. Caps enforce themselves.
            </p>
          </div>
        </div>
      </header>

      <section className="mb-8 flex gap-4 flex-wrap ledger-stagger">
        <StatTile
          label="Today"
          value={`$${todayTotal.toFixed(4)}`}
          sublabel="real-time"
        />
        <StatTile
          label="In range"
          value={`$${totalInRange.toFixed(2)}`}
          sublabel={`${daysInRange} day${daysInRange === 1 ? "" : "s"}`}
        />
        <StatTile
          label="Runs"
          value={runsInRange.toLocaleString()}
          sublabel="AI invocations"
        />
        <StatTile
          label="Avg / run"
          value={`$${runsInRange > 0 ? (totalInRange / runsInRange).toFixed(4) : "0.0000"}`}
          sublabel="rough mean"
        />
      </section>

      <section className="mb-6">
        <DateRangePicker value={range} onChange={setRange} />
      </section>

      {capsQ.data && (
        <section className="mb-8">
          <CostCapBars rows={capsQ.data} />
        </section>
      )}

      {summary.data && (
        <section className="mb-8">
          <DailyCostChart data={summary.data.daily} />
        </section>
      )}

      {summary.data && (
        <section>
          <BreakdownTables summary={summary.data} />
        </section>
      )}
    </main>
  );
}
