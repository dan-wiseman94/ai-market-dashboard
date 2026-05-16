import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

type Row = { date: string; cost_usd: string; runs: number };

export default function DailyCostChart({ data }: { data: Row[] }) {
  if (data.length === 0) {
    return (
      <div className="ledger-surface px-5 py-12 text-center">
        <div className="font-display italic text-ink-400 text-lg">No data in range.</div>
        <div className="font-mono text-[11px] text-ink-500 mt-1">Adjust the range above.</div>
      </div>
    );
  }
  const numeric = data.map((r) => ({
    date: r.date,
    cost: Number(r.cost_usd),
    runs: r.runs,
  }));
  const total = numeric.reduce((a: number, r) => a + r.cost, 0);
  const max = Math.max(...numeric.map((r) => r.cost));
  const avg = total / numeric.length;
  const peak = numeric.find((r) => r.cost === max);

  return (
    <div data-testid="cost-tile-today" className="ledger-surface overflow-hidden">
      <div className="flex items-baseline gap-6 px-5 py-3 border-b border-rule">
        <div>
          <div className="ledger-eyebrow mb-0.5">Daily spend</div>
          <div className="font-display text-[22px] text-ink-50 tabular-nums">
            ${total.toFixed(2)}
          </div>
        </div>
        <div className="h-8 w-px bg-rule-soft" />
        <div>
          <div className="font-mono text-[10px] uppercase tracking-loose2 text-ink-500 mb-0.5">Avg / day</div>
          <div className="font-mono text-[13px] text-ink-200 tabular-nums">${avg.toFixed(4)}</div>
        </div>
        <div className="h-8 w-px bg-rule-soft" />
        <div>
          <div className="font-mono text-[10px] uppercase tracking-loose2 text-ink-500 mb-0.5">Peak</div>
          <div className="font-mono text-[13px] text-ink-200 tabular-nums">
            ${max.toFixed(4)}
            {peak && <span className="text-ink-500 ml-1">· {peak.date.slice(5)}</span>}
          </div>
        </div>
      </div>
      <div data-testid="daily-cost-chart" className="h-64 px-2 py-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={numeric} margin={{ top: 12, right: 12, bottom: 6, left: 0 }}>
            <defs>
              <linearGradient id="copperGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#c89658" stopOpacity={0.55} />
                <stop offset="60%"  stopColor="#c89658" stopOpacity={0.12} />
                <stop offset="100%" stopColor="#c89658" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="0" stroke="rgba(200,150,88,0.08)" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#6b7081"
              tick={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(200,150,88,0.15)" }}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis
              stroke="#6b7081"
              tick={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `$${v.toFixed(2)}`}
              width={56}
            />
            <Tooltip
              cursor={{ stroke: "rgba(200,150,88,0.4)", strokeDasharray: "2 2" }}
              formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
              labelFormatter={(l: string) => l}
              contentStyle={{
                background: "var(--ink-900)",
                border: "1px solid var(--rule-strong)",
                borderRadius: "2px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "11px",
                padding: "8px 10px",
              }}
              labelStyle={{ color: "var(--copper-300)", textTransform: "uppercase", letterSpacing: "0.1em", fontSize: "9px" }}
              itemStyle={{ color: "var(--ink-100)" }}
            />
            <Area
              type="monotone"
              dataKey="cost"
              stroke="#c89658"
              strokeWidth={1.5}
              fill="url(#copperGradient)"
              activeDot={{ r: 3, fill: "#e6ad5e", stroke: "#0b0d12", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
