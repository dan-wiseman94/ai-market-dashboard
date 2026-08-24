import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createExport, deleteExport, exportSingleThread, fetchExports,
  type ExportJob, type ExportScope,
} from "@/api/export";

export function useExports() {
  return useQuery<ExportJob[]>({
    queryKey: ["exports"],
    queryFn: async () => (await fetchExports()).results,
    refetchInterval: (q) => {
      const data = q.state.data as ExportJob[] | undefined;
      return data?.some((j) => j.status === "pending" || j.status === "running") ? 2000 : false;
    },
  });
}

export function useCreateExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scope: ExportScope) => createExport(scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports"] }),
  });
}

export function useExportThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: exportSingleThread,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports"] }),
  });
}

export function useDeleteExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteExport,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports"] }),
  });
}
