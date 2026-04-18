import { useQuery } from "@tanstack/react-query";
import { fetchQuotes } from "@/api/market";

export const useQuotes = (tickers: string[], intervalMs = 3000) =>
  useQuery({
    queryKey: ["quotes", [...tickers].sort().join(",")],
    queryFn: () => fetchQuotes(tickers),
    enabled: tickers.length > 0,
    refetchInterval: tickers.length > 0 ? intervalMs : false,
  });
