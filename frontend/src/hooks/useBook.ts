import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchBookHistory, fetchCurrentBook, recomputeBook } from "@/api/book";

export const useCurrentBook = () =>
  useQuery({ queryKey: ["book", "current"], queryFn: fetchCurrentBook });

/** Newest-first trend rows for the history table. `limit` is part of the key so a
 *  window change refetches rather than serving the previous window from cache. */
export const useBookHistory = (limit = 30) =>
  useQuery({ queryKey: ["book", "history", limit], queryFn: () => fetchBookHistory(limit) });

/** Recompute the book X-ray on demand, then refresh the cached current/history reads. */
export const useRecomputeBook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: recomputeBook,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["book"] }),
  });
};
