import { apiGet, apiPost, apiDelete } from "./client";

export type ExportJob = {
  id: number; created_at: string; completed_at: string | null;
  scope: unknown; format: "zip"; status: "pending" | "running" | "done" | "failed" | "deleted" | "missing";
  filename: string; size_bytes: number | null; sha256: string; error: string;
};

export type ExportScope = {
  threads?: "all" | number[];
  snapshots?: "all" | number[];
  observations?: boolean;
  triggers?: boolean;
  profiles?: boolean;
  watchlists?: boolean;
};

export const fetchExports = () =>
  apiGet<{ count: number; next: string | null; previous: string | null; results: ExportJob[] }>(
    "/api/export/",
  );

export const createExport = (scope: ExportScope) =>
  apiPost<ExportJob>("/api/export/", { scope });

export const exportSingleThread = (threadId: number) =>
  apiPost<ExportJob>(`/api/export/thread/${threadId}/`, {});

export const deleteExport = (id: number) => apiDelete(`/api/export/${id}/`);
