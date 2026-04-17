import { useMutation } from "@tanstack/react-query";
import { CreateSnapshotBody, createSnapshot } from "@/api/snapshots";

export function useCreateSnapshot() {
  return useMutation({
    mutationFn: (body: CreateSnapshotBody) => createSnapshot(body),
  });
}
