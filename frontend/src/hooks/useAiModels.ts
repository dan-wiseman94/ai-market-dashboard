import { useQuery } from "@tanstack/react-query";
import { fetchAiModels } from "@/api/ai";

export const useAiModels = (provider?: string) =>
  useQuery({ queryKey: ["ai-models", provider ?? "all"], queryFn: () => fetchAiModels(provider) });
