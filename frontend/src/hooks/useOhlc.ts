import { useQuery } from "@tanstack/react-query";
import { fetchOhlc } from "@/api/market";

export const useOhlc = (ticker: string, timeframe: string, bars = 60) =>
  useQuery({
    queryKey: ["ohlc", ticker, timeframe, bars],
    queryFn: () => fetchOhlc(ticker, timeframe, bars),
    enabled: !!ticker,
    refetchInterval: 30_000,
  });
