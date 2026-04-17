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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}
