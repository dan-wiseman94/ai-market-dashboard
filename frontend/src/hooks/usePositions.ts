import { useQuery } from "@tanstack/react-query";
import { fetchPositions } from "@/api/market";

export const usePositions = () =>
  useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 10_000,
  });
