import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createJournalEntry,
  listJournal,
  type CreateJournalBody,
} from "@/api/journal";

export function useJournal(threadId: number | null) {
  return useQuery({
    queryKey: ["journal", threadId],
    queryFn: () => listJournal(threadId!),
    enabled: threadId !== null,
  });
}

export function useCreateJournalEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateJournalBody) => createJournalEntry(body),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["journal", variables.thread_id] });
    },
  });
}
