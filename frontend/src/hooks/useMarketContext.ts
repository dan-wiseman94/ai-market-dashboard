import { useQuery } from "@tanstack/react-query";
import { fetchMarketContext } from "@/api/market";

export const useMarketContext = () =>
  useQuery({
    queryKey: ["market-context"],
    queryFn: fetchMarketContext,
    refetchInterval: 30_000,
  });
