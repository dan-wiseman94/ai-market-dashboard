import { useQuery } from "@tanstack/react-query";
import { fetchAiUsage } from "@/api/ai";

export const useAiUsage = () =>
  useQuery({ queryKey: ["ai-usage"], queryFn: fetchAiUsage, refetchInterval: 30_000 });
