import type { WatchlistSymbol } from "@/api/watchlists";
import { useQuotes } from "@/hooks/useQuotes";
import QuoteCell from "./QuoteCell";
import { Link } from "react-router-dom";

type Props = {
  tickers: WatchlistSymbol[];
  onRemove?: (sid: number) => void;
  /** Called with the full symbol-id list in its new order, first to last. */
  onReorder?: (order: number[]) => void;
  /** Disables the move buttons while a reorder is in flight. */
  reorderPending?: boolean;
};

/** The id list with the symbol at `from` moved one slot in `delta`'s direction. */
function moved(tickers: WatchlistSymbol[], from: number, delta: -1 | 1): number[] {
  const ids = tickers.map((s) => s.id);
  const to = from + delta;
  [ids[from], ids[to]] = [ids[to], ids[from]];
  return ids;
}

function ReorderCell({
  tickers,
  index,
  onReorder,
  pending,
}: {
  tickers: WatchlistSymbol[];
  index: number;
  onReorder: (order: number[]) => void;
  pending?: boolean;
}) {
  const ticker = tickers[index].ticker;
  const btn =
    "px-1.5 py-0.5 rounded border border-rule text-ink-400 hover:text-copper-300 " +
    "hover:border-rule-soft disabled:opacity-30 disabled:hover:text-ink-400 text-xs leading-none";
  return (
    <td className="py-2 whitespace-nowrap">
      <button
        type="button"
        onClick={() => onReorder(moved(tickers, index, -1))}
        disabled={pending || index === 0}
        aria-label={`Move ${ticker} up`}
        className={btn}
      >
        ↑
      </button>{" "}
      <button
        type="button"
        onClick={() => onReorder(moved(tickers, index, 1))}
        disabled={pending || index === tickers.length - 1}
        aria-label={`Move ${ticker} down`}
        className={btn}
      >
        ↓
      </button>
    </td>
  );
}

export default function WatchlistTable({
  tickers,
  onRemove,
  onReorder,
  reorderPending,
}: Props) {
  const { data: quotes } = useQuotes(tickers.map((s) => s.ticker));

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-400 text-left">
          {onReorder && (
            <th className="py-2">
              <span className="sr-only">Reorder</span>
            </th>
          )}
          <th className="py-2">Ticker</th>
          <th className="py-2">Last</th>
          <th className="py-2">Bid</th>
          <th className="py-2">Ask</th>
          <th className="py-2">Vol</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {tickers.map((s, i) => {
          const q = quotes?.[s.ticker];
          return (
            <tr key={s.id} className="border-t border-slate-800">
              {onReorder && (
                <ReorderCell
                  tickers={tickers}
                  index={i}
                  onReorder={onReorder}
                  pending={reorderPending}
                />
              )}
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
                  <button onClick={() => onRemove(s.id)} className="text-rose-700 dark:text-rose-400 hover:underline text-xs">
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
