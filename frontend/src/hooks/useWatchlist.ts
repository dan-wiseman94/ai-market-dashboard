import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addSymbol, fetchWatchlist, removeSymbol, reorderSymbols } from "@/api/watchlists";
import type { Watchlist } from "@/api/watchlists";

export const useWatchlist = (id: number | null) =>
  useQuery({
    queryKey: ["watchlist", id],
    queryFn: () => fetchWatchlist(id!),
    enabled: id !== null,
  });

export function useAddSymbol(wid: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => addSymbol(wid, ticker),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist", wid] }),
  });
}

export function useRemoveSymbol(wid: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: number) => removeSymbol(wid, sid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist", wid] }),
  });
}

/**
 * Persist a new symbol order (an array of WatchlistSymbol ids, first to last).
 *
 * The reorder endpoint answers `{ok: true}`, not the reordered watchlist, so the
 * cache is rewritten optimistically: without it the row the user just moved
 * snaps back to its old slot until the refetch lands, which reads as a failed
 * click. `onError` restores the snapshot and `onSettled` refetches so the server
 * stays the source of truth.
 */
export function useReorderSymbols(wid: number) {
  const qc = useQueryClient();
  const key = ["watchlist", wid];
  return useMutation({
    mutationFn: (order: number[]) => reorderSymbols(wid, order),
    onMutate: async (order: number[]) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Watchlist>(key);
      if (prev) {
        const bySid = new Map(prev.tickers.map((s) => [s.id, s]));
        const next = order
          .map((sid) => bySid.get(sid))
          .filter((s): s is Watchlist["tickers"][number] => s !== undefined)
          .map((s, idx) => ({ ...s, sort_order: idx }));
        qc.setQueryData<Watchlist>(key, { ...prev, tickers: next });
      }
      return { prev };
    },
    onError: (_err, _order, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
