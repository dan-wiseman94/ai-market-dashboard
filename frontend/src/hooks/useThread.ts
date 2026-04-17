import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchThread, fetchThreads, sendMessage } from "@/api/threads";

export const useThreads = () => useQuery({ queryKey: ["threads"], queryFn: fetchThreads });

export const useThread = (id: number | null) =>
  useQuery({
    queryKey: ["thread", id],
    queryFn: () => fetchThread(id!),
    enabled: id !== null,
  });

export function useSendMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => sendMessage(threadId, text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}
