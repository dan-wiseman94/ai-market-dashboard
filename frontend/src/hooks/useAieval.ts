import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchEvalRuns, triggerEvalRun } from "@/api/aieval";

/** Persisted eval runs, newest first. Polls only while a queued run is expected. */
export function useEvalRuns(opts: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: ["aieval/runs"],
    queryFn: fetchEvalRuns,
    refetchInterval: opts.refetchInterval ?? false,
  });
}

export function useTriggerEvalRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: triggerEvalRun,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aieval/runs"] });
      qc.invalidateQueries({ queryKey: ["aieval/latest"] });
    },
  });
}
