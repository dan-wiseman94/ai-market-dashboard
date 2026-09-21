import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchWatchlists, createWatchlist, renameWatchlist, deleteWatchlist,
} from "@/api/watchlists";

export const useWatchlists = () =>
  useQuery({ queryKey: ["watchlists"], queryFn: fetchWatchlists });

export function useCreateWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createWatchlist(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useRenameWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameWatchlist(id, name),
    // The detail page reads ["watchlist", id] — a rename from either surface has
    // to refresh both or the other one keeps showing the stale name.
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["watchlists"] });
      qc.invalidateQueries({ queryKey: ["watchlist", id] });
    },
  });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}
