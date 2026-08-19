import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/api/client";

export interface ErrorRow {
  id: number;
  level: string;
  source: string;
  message: string;
  fingerprint: string;
  resolved: boolean;
  created_at: string;
}

export function useErrors(unresolved = false) {
  return useQuery({
    queryKey: ["errors", unresolved],
    queryFn: () =>
      apiGet<{ results: ErrorRow[]; count: number }>(
        `/api/errors/?unresolved=${unresolved}`,
      ),
  });
}

export function useResolveError() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiPost(`/api/errors/${id}/resolve/`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["errors"] }),
  });
}
