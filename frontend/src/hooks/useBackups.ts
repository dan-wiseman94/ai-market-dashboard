import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteBackup, fetchBackups, runBackupNow, type Backup } from "@/api/backups";

export function useBackups() {
  return useQuery<Backup[]>({
    queryKey: ["backups"],
    queryFn: async () => (await fetchBackups()).results,
  });
}

export function useRunBackupNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runBackupNow,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useDeleteBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteBackup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}
