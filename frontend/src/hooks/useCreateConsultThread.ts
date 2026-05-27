import { useMutation } from "@tanstack/react-query";
import { createThread } from "@/api/threads";

export function useCreateConsultThread() {
  return useMutation({
    mutationFn: (body: {
      profile_id?: number;
      pinned_snapshot_id?: number;
      title?: string;
      auto_reply?: boolean;
    }) => createThread({ kind: "consult", ...body }),
  });
}
