import { apiGet, apiPost, apiDelete } from "./client";

export type Backup = {
  id: number; created_at: string; filename: string; size_bytes: number;
  sha256: string; kind: "scheduled" | "manual"; status: string; error: string;
};

export const fetchBackups = () =>
  apiGet<{ count: number; next: string | null; previous: string | null; results: Backup[] }>(
    "/api/backups/",
  );

export const runBackupNow = () => apiPost<{ queued: boolean }>("/api/backups/run/", {});

export const deleteBackup = (id: number) => apiDelete(`/api/backups/${id}/`);
