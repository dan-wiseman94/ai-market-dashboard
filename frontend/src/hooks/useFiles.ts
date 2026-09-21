import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  attachFileToThread,
  deleteFile,
  fetchFiles,
  uploadFile,
} from "@/api/threads";

export type { UserFile } from "@/api/threads";

export function useFiles(kind?: string) {
  return useQuery({
    queryKey: ["files", kind ?? ""],
    queryFn: () => fetchFiles(kind),
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => uploadFile(form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

/**
 * Delete a file. The backend also deletes the upstream object at the provider
 * (Anthropic Files API) — the row and the remote file go together, so the
 * caller must confirm before invoking this.
 */
export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileId: number) => deleteFile(fileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useAttachFileToThread(threadId: number) {
  return useMutation({
    mutationFn: ({ fileId, prompt }: { fileId: number; prompt: string }) =>
      attachFileToThread(threadId, { file_id: fileId, prompt }),
  });
}
