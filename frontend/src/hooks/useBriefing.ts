import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBriefingConfig, fetchLatestBriefing, patchBriefingConfig, runBriefingNow,
  type BriefingConfig,
} from "@/api/briefing";

export const useLatestBriefing = () =>
  useQuery({ queryKey: ["briefing-latest"], queryFn: fetchLatestBriefing, refetchInterval: 60_000 });

export const useRunBriefing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runBriefingNow,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing-latest"] }),
  });
};

export const useBriefingConfig = () => {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["briefing-config"], queryFn: fetchBriefingConfig });
  const update = useMutation({
    mutationFn: (b: Partial<BriefingConfig>) => patchBriefingConfig(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing-config"] }),
  });
  return { ...query, update };
};
