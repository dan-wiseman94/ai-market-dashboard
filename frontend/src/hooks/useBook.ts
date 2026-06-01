import { useQuery } from "@tanstack/react-query";

import { fetchBookHistory, fetchCurrentBook } from "@/api/book";

export const useCurrentBook = () =>
  useQuery({ queryKey: ["book", "current"], queryFn: fetchCurrentBook });
export const useBookHistory = () =>
  useQuery({ queryKey: ["book", "history"], queryFn: fetchBookHistory });
