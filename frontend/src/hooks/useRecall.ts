import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { recallBackfill, recallRelated, recallSearch, recallStatus } from "@/api/recall";
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

/**
 * Index health.
 *
 * `queuedAt` (epoch ms) turns on polling after a backfill: the task emits no
 * completion event, so re-reading the counts is the only way progress shows.
 * Polling stops after POLL_WINDOW_MS rather than running forever.
 */
const POLL_EVERY_MS = 5_000;
const POLL_WINDOW_MS = 2 * 60_000;

export function useRecallStatus(queuedAt: number | null = null) {
  return useQuery({
    queryKey: ["recall/status"],
    queryFn: recallStatus,
    refetchInterval: () => {
      if (queuedAt === null) return false;
      return Date.now() - queuedAt > POLL_WINDOW_MS ? false : POLL_EVERY_MS;
    },
  });
}

/** Queue the re-embed of everything pending semantic indexing. */
export function useRecallBackfill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: recallBackfill,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["recall/status"] });
    },
  });
}
