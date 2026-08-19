import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPostForm } from "@/api/client";

export interface UserFile {
  id: number;
  anthropic_id?: string;
  kind: string;
  ticker: string;
  mime: string;
  size: number;
  filename: string;
}

export function useFiles(kind?: string) {
  return useQuery({
    queryKey: ["files", kind ?? ""],
    queryFn: async (): Promise<UserFile[]> => {
      const params = kind ? `?kind=${encodeURIComponent(kind)}` : "";
      const body = await apiGet<{ results?: UserFile[] } | null>(`/api/files/${params}`);
      return body?.results ?? [];
    },
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => apiPostForm<UserFile>("/api/files/", form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useAttachFileToThread(threadId: number) {
  return useMutation({
    mutationFn: ({ fileId, prompt }: { fileId: number; prompt: string }) =>
      apiPost<{ message_id: number }>(`/api/threads/${threadId}/attach-file/`, {
        file_id: fileId,
        prompt,
      }),
  });
}
