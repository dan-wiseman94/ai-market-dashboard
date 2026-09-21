import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFeatures, saveFeatureValue, type FeatureValue } from "@/api/features";

export const useFeatures = () =>
  useQuery({
    queryKey: ["features"],
    queryFn: fetchFeatures,
    staleTime: 30_000,
  });

export interface SaveFeatureVars {
  /** The row being written — used to disable only that row while it is in flight. */
  key: string;
  writePath: string;
  field: string;
  value: FeatureValue;
}

/**
 * One mutation for every row: the payload says where each write goes, so the page
 * never hardcodes an endpoint.
 *
 * Saving is per-row and immediate rather than draft-plus-save. `PATCH /api/settings/`
 * rejects the whole body on the first invalid field and writes nothing, so batching
 * ~90 rows would let one bad value silently discard every other change.
 */
export const useSaveFeature = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveFeatureVars) => saveFeatureValue(v.writePath, v.field, v.value),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["features"] });
      // The same rows are read by the System settings page and the TradingView
      // tools toggle in Connections; keep them from showing a stale value.
      void qc.invalidateQueries({ queryKey: ["system-settings"] });
      void qc.invalidateQueries({ queryKey: ["briefing-config"] });
    },
  });
};
