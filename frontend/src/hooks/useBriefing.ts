import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBriefingConfig, fetchBriefings, fetchLatestBriefing, patchBriefingConfig, runBriefingNow,
  type BriefingConfig,
} from "@/api/briefing";

export const useLatestBriefing = () =>
  useQuery({ queryKey: ["briefing-latest"], queryFn: fetchLatestBriefing, refetchInterval: 60_000 });

/** Paginated briefing history (newest first). The page number is part of the key. */
export const useBriefings = (page = 1) =>
  useQuery({ queryKey: ["briefings", page], queryFn: () => fetchBriefings(page) });

export const useRunBriefing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runBriefingNow,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["briefing-latest"] });
      void qc.invalidateQueries({ queryKey: ["briefings"] });
    },
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
