import { useQuery } from "@tanstack/react-query";
import { recallRelated, recallSearch } from "@/api/recall";
import type { RecallSearchParams } from "@/api/recall";

export interface RecallFilters {
  kind?: string;
  ticker?: string;
  k?: number;
}

export function useRecall(q: string, filters: RecallFilters = {}) {
  const params: RecallSearchParams = {
    q,
    kind: filters.kind,
    ticker: filters.ticker,
    k: filters.k,
  };
  return useQuery({
    queryKey: ["recall/search", q, filters],
    queryFn: () => recallSearch(params),
    enabled: q.trim().length > 0,
  });
}

export function useRelated(kind: string, id: number) {
  return useQuery({
    queryKey: ["recall/related", kind, id],
    queryFn: () => recallRelated({ kind, id, k: 5 }),
    enabled: !!kind && id > 0,
  });
}
