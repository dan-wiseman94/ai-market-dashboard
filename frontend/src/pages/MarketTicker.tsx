import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuotes } from "@/hooks/useQuotes";
import { useOhlc } from "@/hooks/useOhlc";
import QuoteCell from "@/components/QuoteCell";
import { format } from "date-fns";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"];

export default function MarketTicker() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const T = ticker.toUpperCase();
  const [tf, setTf] = useState("1m");
  const { data: quotes } = useQuotes([T]);
  const { data: ohlc } = useOhlc(T, tf, 60);

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{T}</h1>
        <Link to="/" className="text-sm text-slate-300 hover:underline">← Dashboard</Link>
      </div>

      <div className="text-xl"><QuoteCell q={quotes?.[T]} /></div>

      <div className="flex gap-2">
        {TIMEFRAMES.map((x) => (
          <button
            key={x}
            onClick={() => setTf(x)}
            className={`px-2 py-1 rounded text-sm ${
              tf === x ? "bg-slate-600" : "bg-slate-800 hover:bg-slate-700"
            }`}
          >
            {x}
          </button>
        ))}
      </div>

      <div className="max-h-[480px] overflow-y-auto border border-slate-800 rounded">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 sticky top-0">
            <tr className="text-slate-400 text-left">
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Open</th>
              <th className="px-3 py-2">High</th>
              <th className="px-3 py-2">Low</th>
              <th className="px-3 py-2">Close</th>
              <th className="px-3 py-2">Volume</th>
            </tr>
          </thead>
          <tbody>
            {(ohlc?.bars ?? []).slice().reverse().map((b) => (
              <tr key={b.ts} className="border-t border-slate-800">
                <td className="px-3 py-1.5 tabular-nums text-slate-400">{format(new Date(b.ts), "MMM d HH:mm")}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.open.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.high.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.low.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums">{b.close.toFixed(2)}</td>
                <td className="px-3 py-1.5 tabular-nums text-slate-400">{b.volume.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
