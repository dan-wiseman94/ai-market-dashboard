import { useQuery } from "@tanstack/react-query";
import { fetchSchwabStatus, fetchSchwabAppConfig } from "@/api/schwab";

export const useSchwabStatus = () =>
  useQuery({
    queryKey: ["schwab", "status"],
    queryFn: fetchSchwabStatus,
    staleTime: 10_000,
  });

export const useSchwabAppConfig = () =>
  useQuery({
    queryKey: ["schwab", "app-config"],
    queryFn: fetchSchwabAppConfig,
    staleTime: 10_000,
  });
