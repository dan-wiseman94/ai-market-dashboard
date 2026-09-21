import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteBackup,
  fetchBackups,
  restoreBackup,
  runBackupNow,
  type Backup,
  type RestoreResponse,
} from "@/api/backups";

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

export type RestoreVars = { id: number; confirm: string };

/**
 * Restore the database from a backup.
 *
 * A restore replaces the *entire* database, so every cached query in the app is
 * stale the moment it lands — not just `["backups"]`. The unfiltered
 * `invalidateQueries()` is deliberate: anything narrower leaves the UI showing
 * rows that no longer exist.
 */
export function useRestoreBackup() {
  const qc = useQueryClient();
  return useMutation<RestoreResponse, Error, RestoreVars>({
    mutationFn: ({ id, confirm }) => restoreBackup(id, confirm),
    onSuccess: () => qc.invalidateQueries(),
  });
}
