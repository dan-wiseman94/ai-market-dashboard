import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
      const resp = await fetch(`/api/files/${params}`);
      if (!resp.ok) throw new Error("Failed to fetch files");
      const body = await resp.json();
      return body.results ?? [];
    },
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (form: FormData) => {
      const resp = await fetch("/api/files/", { method: "POST", body: form });
      if (!resp.ok) throw new Error("Upload failed");
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useAttachFileToThread(threadId: number) {
  return useMutation({
    mutationFn: async ({ fileId, prompt }: { fileId: number; prompt: string }) => {
      const resp = await fetch(`/api/threads/${threadId}/attach-file/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId, prompt }),
      });
      if (!resp.ok) throw new Error("Attach failed");
      return resp.json();
    },
  });
}
