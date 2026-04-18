import { useQuery } from "@tanstack/react-query";
import {
  fetchCostsToday,
  fetchCostsSummary, fetchCostsCaps, fetchCostsSnapshot,
  type CostsSummary, type CapRow, type SnapshotBreakdownRow,
} from "@/api/costs";

export const useCostsToday = () =>
  useQuery({ queryKey: ["costs-today"], queryFn: fetchCostsToday, refetchInterval: 30_000 });

export function useCostsSummary(range: { from: string; to: string }) {
  return useQuery<CostsSummary>({
    queryKey: ["costs-summary", range.from, range.to],
    queryFn: () => fetchCostsSummary(range),
  });
}

export function useCostsCaps() {
  return useQuery<CapRow[]>({ queryKey: ["costs-caps"], queryFn: fetchCostsCaps });
}

export function useCostsSnapshot(snapshotId: number | null) {
  return useQuery<SnapshotBreakdownRow[]>({
    queryKey: ["costs-snapshot", snapshotId],
    queryFn: () => fetchCostsSnapshot(snapshotId!),
    enabled: snapshotId !== null,
  });
}
