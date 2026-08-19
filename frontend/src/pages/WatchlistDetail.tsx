import { useState } from "react";
import { useParams } from "react-router-dom";
import WatchlistTable from "@/components/WatchlistTable";
import { SkeletonRows } from "@/components/Skeleton";
import { TickerChanges } from "./watchlist/TickerChanges";
import { useAddSymbol, useRemoveSymbol, useWatchlist } from "@/hooks/useWatchlist";

export default function WatchlistDetail() {
  const { id } = useParams<{ id: string }>();
  const wid = id ? parseInt(id, 10) : null;
  const { data: wl, isLoading } = useWatchlist(wid);
  const add = useAddSymbol(wid ?? 0);
  const remove = useRemoveSymbol(wid ?? 0);
  const [ticker, setTicker] = useState("");

  if (!wid) return <main className="p-6">Invalid watchlist</main>;
  if (isLoading || !wl) {
    return (
      <main className="p-6 max-w-4xl mx-auto">
        <SkeletonRows rows={6} />
      </main>
    );
  }

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">{wl.name}</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ticker.trim()) return;
          add.mutate(ticker.trim().toUpperCase(), {
            onSuccess: () => setTicker(""),
          });
        }}
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Add ticker (e.g. SPY)"
          className="flex-1 px-3 py-1.5 rounded bg-ink-900 border border-rule"
        />
        <button className="px-3 py-1.5 rounded bg-gain-500 hover:bg-gain-400">Add</button>
      </form>
      {add.isError && (
        <p className="text-loss-400 text-sm">{(add.error as Error).message}</p>
      )}

      <WatchlistTable symbols={wl.symbols} onRemove={(sid) => remove.mutate(sid)} />

      {wl.symbols.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold text-ink-300">
            What changed since your last look
          </h2>
          <div className="ledger-surface px-4">
            {wl.symbols.map((s) => (
              <TickerChanges key={s.id} ticker={s.ticker} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
