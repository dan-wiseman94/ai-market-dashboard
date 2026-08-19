import { useQuery } from "@tanstack/react-query";

import { getCalendarStatus } from "@/api/market";

export function useMarketStatus(symbols: string[] = []) {
  return useQuery({
    queryKey: ["market-status", [...symbols].sort()],
    queryFn: () => getCalendarStatus(symbols),
    refetchInterval: 60_000,
  });
}
