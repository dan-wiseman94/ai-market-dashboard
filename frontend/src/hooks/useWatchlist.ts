import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addSymbol, fetchWatchlist, removeSymbol } from "@/api/watchlists";

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
