import { useQuery } from "@tanstack/react-query";
import { fetchSchwabStatus } from "@/api/schwab";

export const useSchwabStatus = () =>
  useQuery({
    queryKey: ["schwab", "status"],
    queryFn: fetchSchwabStatus,
    staleTime: 10_000,
  });
