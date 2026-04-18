import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

type Row = { date: string; cost_usd: string; runs: number };

export default function DailyCostChart({ data }: { data: Row[] }) {
  if (data.length === 0) {
    return <div className="p-6 text-center text-slate-500 border border-slate-800 rounded">No data in range</div>;
  }
  const numeric = data.map((r) => ({ date: r.date, cost: Number(r.cost_usd) }));
  return (
    <div data-testid="daily-cost-chart" className="h-64 border border-slate-800 rounded p-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={numeric} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 10 }} />
          <YAxis stroke="#64748b" tick={{ fontSize: 10 }}
                 tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
          <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`}
                   contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
          <Line type="monotone" dataKey="cost" stroke="#34d399" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
