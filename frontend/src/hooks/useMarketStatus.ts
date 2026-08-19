import { useQuery } from "@tanstack/react-query";

import { getCalendarStatus } from "@/api/market";

export function useMarketStatus(tickers: string[] = []) {
  return useQuery({
    queryKey: ["market-status", [...tickers].sort()],
    queryFn: () => getCalendarStatus(tickers),
    refetchInterval: 60_000,
  });
}
