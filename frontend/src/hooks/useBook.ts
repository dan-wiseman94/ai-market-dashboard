import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchBookHistory, fetchCurrentBook, recomputeBook } from "@/api/book";

export const useCurrentBook = () =>
  useQuery({ queryKey: ["book", "current"], queryFn: fetchCurrentBook });
/** @public — book-history query hook (parallels useCurrentBook); awaits a history view. */
export const useBookHistory = () =>
  useQuery({ queryKey: ["book", "history"], queryFn: fetchBookHistory });

/** Recompute the book X-ray on demand, then refresh the cached current/history reads. */
export const useRecomputeBook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: recomputeBook,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["book"] }),
  });
};
