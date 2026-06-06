import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchCurrentRegime, fetchRegimeHistory, refreshRegime } from "@/api/regime";

export const useCurrentRegime = () =>
  useQuery({ queryKey: ["regime", "current"], queryFn: fetchCurrentRegime });

export const useRegimeHistory = () =>
  useQuery({ queryKey: ["regime", "history"], queryFn: fetchRegimeHistory });

/** Refresh the market-regime reading on demand, then refresh cached current/history reads. */
export const useRefreshRegime = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshRegime,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regime"] }),
  });
};
