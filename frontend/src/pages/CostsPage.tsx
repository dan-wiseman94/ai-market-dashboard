import { useState } from "react";
import CostCapBars from "@/components/costs/CostCapBars";
import DateRangePicker, { type Range } from "@/components/costs/DateRangePicker";
import DailyCostChart from "@/components/costs/DailyCostChart";
import BreakdownTables from "@/components/costs/BreakdownTables";
import { useCostsSummary, useCostsCaps } from "@/hooks/useCosts";

function defaultRange(): Range {
  const now = new Date();
  const start = new Date(now.getTime() - 30 * 86400000);
  return { from: start.toISOString(), to: now.toISOString() };
}

export default function CostsPage() {
  const [range, setRange] = useState<Range>(defaultRange);
  const summary = useCostsSummary(range);
  const capsQ = useCostsCaps();

  const csvHref = `/api/costs/export.csv?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`;

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Costs</h1>
        <a
          href={csvHref}
          className="text-sm px-3 py-1 rounded bg-slate-800 hover:bg-slate-700"
        >
          ⇣ Export CSV
        </a>
      </div>
      <DateRangePicker value={range} onChange={setRange} />
      {capsQ.data && <CostCapBars rows={capsQ.data} />}
      {summary.data && <DailyCostChart data={summary.data.daily} />}
      {summary.data && <BreakdownTables summary={summary.data} />}
    </main>
  );
}
