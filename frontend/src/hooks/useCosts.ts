import { useQuery } from "@tanstack/react-query";
import { fetchCostsToday } from "@/api/costs";

export const useCostsToday = () =>
  useQuery({ queryKey: ["costs-today"], queryFn: fetchCostsToday, refetchInterval: 30_000 });
