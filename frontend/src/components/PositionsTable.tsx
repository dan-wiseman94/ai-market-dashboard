import { usePositions } from "@/hooks/usePositions";

export default function PositionsTable() {
  const { data, isLoading, error } = usePositions();
  if (error) return <p className="text-rose-400 text-sm">Could not load positions: {(error as Error).message}</p>;
  if (isLoading) return <p>Loading positions…</p>;
  if (!data?.length) return <p className="text-slate-400">No open positions.</p>;

  const totalPl = data.reduce((s, p) => s + (p.unrealized_pl ?? 0), 0);
  const totalDay = data.reduce((s, p) => s + (p.day_pl ?? 0), 0);

  const plClass = (n: number) => (n >= 0 ? "text-emerald-400" : "text-rose-400");

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-400 text-left">
          <th className="py-2">Ticker</th>
          <th className="py-2">Qty</th>
          <th className="py-2">Avg</th>
          <th className="py-2">Value</th>
          <th className="py-2">Day P/L</th>
          <th className="py-2">Unrealized</th>
        </tr>
      </thead>
      <tbody>
        {data.map((p) => (
          <tr key={p.ticker} className="border-t border-slate-800">
            <td className="py-2 font-medium">{p.ticker}</td>
            <td className="py-2 tabular-nums">{p.qty}</td>
            <td className="py-2 tabular-nums">{p.avg_cost?.toFixed(2) ?? "—"}</td>
            <td className="py-2 tabular-nums">{p.mkt_value?.toFixed(2) ?? "—"}</td>
            <td className={`py-2 tabular-nums ${plClass(p.day_pl ?? 0)}`}>
              {p.day_pl?.toFixed(2) ?? "—"}
            </td>
            <td className={`py-2 tabular-nums ${plClass(p.unrealized_pl ?? 0)}`}>
              {p.unrealized_pl?.toFixed(2) ?? "—"}
            </td>
          </tr>
        ))}
        <tr className="border-t border-slate-700 font-semibold">
          <td colSpan={4} className="py-2 text-right">Totals</td>
          <td className={`py-2 tabular-nums ${plClass(totalDay)}`}>
            {totalDay.toFixed(2)}
          </td>
          <td className={`py-2 tabular-nums ${plClass(totalPl)}`}>
            {totalPl.toFixed(2)}
          </td>
        </tr>
      </tbody>
    </table>
  );
}
