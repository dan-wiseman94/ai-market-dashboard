import { useMutation, useQuery } from "@tanstack/react-query";

import { actDeskEntry, dismissDeskEntry, fetchDeskFeed, runDeskSweep } from "@/api/desk";

export const useDeskFeed = () => useQuery({ queryKey: ["desk", "feed"], queryFn: fetchDeskFeed });
export const useRunDeskSweep = () => useMutation({ mutationFn: runDeskSweep });
export const useActDeskEntry = () =>
  useMutation({ mutationFn: ({ id, action }: { id: number; action: string }) => actDeskEntry(id, action) });
export const useDismissDeskEntry = () => useMutation({ mutationFn: dismissDeskEntry });
