import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useCreateWatchlist, useDeleteWatchlist, useWatchlists } from "@/hooks/useWatchlists";

export default function WatchlistsList() {
  const { data, isLoading } = useWatchlists();
  const create = useCreateWatchlist();
  const del = useDeleteWatchlist();
  const [name, setName] = useState("");

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Watchlists</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          create.mutate(name.trim(), { onSuccess: () => setName("") });
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New watchlist name"
          className="flex-1 px-3 py-1.5 rounded bg-ink-900 border border-rule"
        />
        <button className="px-3 py-1.5 rounded bg-gain-500 hover:bg-gain-400">Create</button>
      </form>

      {isLoading ? (
        <SkeletonRows rows={4} />
      ) : (data ?? []).length === 0 ? (
        <EmptyState
          title="No watchlists yet"
          body="Create one above to start tracking a group of tickers."
        />
      ) : (
        <ul className="space-y-1">
          {(data ?? []).map((w) => (
            <li key={w.id} data-testid={`watchlist-row-${w.name}`} className="flex items-center justify-between p-3 rounded border border-rule">
              <Link to={`/watchlists/${w.id}`} className="hover:underline">
                {w.name} <span className="text-ink-500 text-sm">({w.symbols.length} symbols)</span>
              </Link>
              <button
                onClick={() => del.mutate(w.id)}
                className="text-loss-400 text-sm hover:underline"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
