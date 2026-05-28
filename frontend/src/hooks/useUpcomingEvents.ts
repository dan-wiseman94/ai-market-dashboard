import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingEvents } from "@/api/market";

export const useUpcomingEvents = (tickers: string[] = [], withinDays = 14) =>
  useQuery({
    queryKey: ["upcoming-events", tickers, withinDays],
    queryFn: () => fetchUpcomingEvents(tickers, withinDays),
    refetchInterval: 300_000,
  });
