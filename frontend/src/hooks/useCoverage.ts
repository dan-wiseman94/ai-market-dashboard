import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/api/client";

export type Stance = "bull" | "bear" | "neutral";

export interface CoverageRevision {
  id: number;
  prior: Partial<CoverageSnapshot>;
  new: Partial<CoverageSnapshot>;
  reason: string;
  source_snapshot_id: number | null;
  created_at: string;
}

/** The mutable fields of a note, as captured in a revision's prior/new blobs. */
export interface CoverageSnapshot {
  stance: Stance;
  conviction: number;
  bull_case: string;
  bear_case: string;
  key_levels: Record<string, number | string>;
  watching_for: string;
}

export interface CoverageNote extends CoverageSnapshot {
  id: number;
  ticker: string;
  created_at: string;
  updated_at: string;
  revisions: CoverageRevision[];
}

/** Row shape for the coverage index endpoint — enough to rank and route on, without
 * the case text. `revision_count` / `last_revised_at` are annotated server-side. */
export interface CoverageListRow {
  id: number;
  ticker: string;
  stance: Stance;
  conviction: number;
  revision_count: number;
  last_revised_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Every covered ticker, for the index. */
export function useCoverageIndex() {
  return useQuery({
    queryKey: ["coverage"],
    queryFn: () => apiGet<CoverageListRow[]>("/api/coverage/"),
  });
}

/** The full house view for one ticker, with its revision history. */
export function useCoverage(ticker: string) {
  return useQuery({
    queryKey: ["coverage", ticker],
    queryFn: () =>
      apiGet<CoverageNote>(`/api/coverage/${encodeURIComponent(ticker)}/`),
    enabled: Boolean(ticker),
    retry: false,
  });
}

export interface ReviseResponse {
  revised: boolean;
  note: CoverageNote | null;
}

/** Re-run the AI against the latest snapshot; invalidates the note on success. */
export function useReviseCoverage(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<ReviseResponse>(
        `/api/coverage/${encodeURIComponent(ticker)}/revise/`,
      ),
    // Invalidate the whole "coverage" root, not just this ticker: a revision moves
    // the stance/conviction the index ranks on, and a first revision creates the row.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coverage"] }),
  });
}
