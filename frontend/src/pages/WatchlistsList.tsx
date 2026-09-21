import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  useCreateWatchlist,
  useDeleteWatchlist,
  useRenameWatchlist,
  useWatchlists,
} from "@/hooks/useWatchlists";
import { RenameWatchlist } from "./watchlist/RenameWatchlist";
import type { Watchlist } from "@/api/watchlists";

function WatchlistRow({
  watchlist,
  onRename,
  onDelete,
  renamePending,
}: {
  watchlist: Watchlist;
  onRename: (name: string) => void;
  onDelete: () => void;
  renamePending: boolean;
}) {
  return (
    <li
      data-testid={`watchlist-row-${watchlist.name}`}
      className="flex items-center justify-between gap-3 p-3 rounded border border-rule"
    >
      <RenameWatchlist
        name={watchlist.name}
        onSave={onRename}
        pending={renamePending}
        className="flex-1 min-w-0"
      >
        <Link to={`/watchlists/${watchlist.id}`} className="hover:underline truncate">
          {watchlist.name}{" "}
          <span className="text-ink-500 text-sm">({watchlist.tickers.length} symbols)</span>
        </Link>
      </RenameWatchlist>
      <button
        onClick={onDelete}
        aria-label={`Delete ${watchlist.name}`}
        className="text-loss-400 text-sm hover:underline shrink-0"
      >
        Delete
      </button>
    </li>
  );
}

export default function WatchlistsList() {
  const { data, isLoading } = useWatchlists();
  const create = useCreateWatchlist();
  const rename = useRenameWatchlist();
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
          aria-label="New watchlist name"
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
            <WatchlistRow
              key={w.id}
              watchlist={w}
              renamePending={rename.isPending}
              onRename={(next) => rename.mutate({ id: w.id, name: next })}
              onDelete={() => del.mutate(w.id)}
            />
          ))}
        </ul>
      )}
    </main>
  );
}
