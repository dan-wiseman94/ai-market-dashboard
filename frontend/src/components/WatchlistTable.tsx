import type { WatchlistSymbol } from "@/api/watchlists";
import { useQuotes } from "@/hooks/useQuotes";
import QuoteCell from "./QuoteCell";
import { Link } from "react-router-dom";

type Props = {
  symbols: WatchlistSymbol[];
  onRemove?: (sid: number) => void;
};

export default function WatchlistTable({ symbols, onRemove }: Props) {
  const tickers = symbols.map((s) => s.ticker);
  const { data: quotes } = useQuotes(tickers);

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-400 text-left">
          <th className="py-2">Ticker</th>
          <th className="py-2">Last</th>
          <th className="py-2">Bid</th>
          <th className="py-2">Ask</th>
          <th className="py-2">Vol</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {symbols.map((s) => {
          const q = quotes?.[s.ticker];
          return (
            <tr key={s.id} className="border-t border-slate-800">
              <td className="py-2">
                <Link to={`/market/${s.ticker}`} className="hover:underline font-medium">
                  {s.ticker}
                </Link>
              </td>
              <td className="py-2"><QuoteCell q={q} /></td>
              <td className="py-2 tabular-nums text-slate-300">{q?.bid?.toFixed(2) ?? "—"}</td>
              <td className="py-2 tabular-nums text-slate-300">{q?.ask?.toFixed(2) ?? "—"}</td>
              <td className="py-2 tabular-nums text-slate-400">{q?.volume?.toLocaleString() ?? "—"}</td>
              <td className="py-2">
                {onRemove && (
                  <button onClick={() => onRemove(s.id)} className="text-rose-400 hover:underline text-xs">
                    Remove
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
