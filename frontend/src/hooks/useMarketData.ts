import { useQuery } from "@tanstack/react-query";
import { fetchMacro, fetchTreasury, fetchFilings } from "@/api/market";

const FIVE_MIN = 5 * 60_000;

export const useMacro = () =>
  useQuery({ queryKey: ["market", "macro"], queryFn: fetchMacro, staleTime: FIVE_MIN });

export const useTreasury = () =>
  useQuery({ queryKey: ["market", "treasury"], queryFn: fetchTreasury, staleTime: FIVE_MIN });

export const useFilings = (tickers: string[]) =>
  useQuery({
    queryKey: ["market", "filings", tickers],
    queryFn: () => fetchFilings(tickers),
    enabled: tickers.length > 0,
    staleTime: FIVE_MIN,
  });
