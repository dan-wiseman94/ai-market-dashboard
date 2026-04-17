import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "@/api/snapshots";

export const useSnapshot = (id: number | null) =>
  useQuery({
    queryKey: ["snapshot", id],
    queryFn: () => fetchSnapshot(id!),
    enabled: id !== null,
  });
