import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  compareMessage,
  fetchThread,
  fetchThreads,
  renameThread,
  sendMessage,
  stopMessage,
} from "@/api/threads";

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
    mutationFn: (args: { text: string; override?: { provider: string; model: string } }) =>
      sendMessage(threadId, args.text, args.override),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}

export function useCompareMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { text: string; branches: {provider: string; model: string}[] }) =>
      compareMessage(threadId, args.text, args.branches),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}

export function useStopMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (messageId: number) => stopMessage(threadId, messageId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}

export function useRenameThread(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) => renameThread(threadId, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["thread", threadId] });
      qc.invalidateQueries({ queryKey: ["threads"] });
    },
  });
}
