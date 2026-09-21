import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveThesis,
  closeThesis,
  createThesis,
  getThesis,
  listTheses,
  purgeThesis,
  restoreThesis,
  runPostmortem,
  updateThesis,
  type CloseThesisBody,
  type CreateThesisBody,
  type Thesis,
  type ThesisListFilter,
} from "@/api/thesis";

export function useTheses(filter: ThesisListFilter = "live") {
  return useQuery({
    // The filter is part of the key so "Archived" is its own cache entry rather
    // than overwriting the live list. Invalidating ["theses"] still hits all of
    // them (react-query matches on key prefix).
    queryKey: ["theses", { filter }],
    queryFn: () => listTheses(filter),
  });
}

export function useThesis(id: number | null) {
  return useQuery({
    queryKey: ["theses", id],
    queryFn: () => getThesis(id!),
    enabled: id !== null,
  });
}

export function useCreateThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateThesisBody) => createThesis(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["theses"] }),
  });
}

export function useCloseThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: CloseThesisBody }) =>
      closeThesis(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["theses"] });
      qc.invalidateQueries({ queryKey: ["theses", id] });
    },
  });
}

/** Reversible: DELETE archives the thesis and keeps its post-mortem history. */
export function useArchiveThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => archiveThesis(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["theses"] });
      qc.invalidateQueries({ queryKey: ["theses", id] });
    },
  });
}

export function useRestoreThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => restoreThesis(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["theses"] });
      qc.invalidateQueries({ queryKey: ["theses", id] });
    },
  });
}

/**
 * Destructive: drops the row. Rejects with a 409 ApiError
 * (`code === "postmortem_history"`) when completed post-mortems exist, so the
 * caller must render the error rather than assume success.
 */
export function usePurgeThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => purgeThesis(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["theses"] }),
  });
}

export function useRunPostmortem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => runPostmortem(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["theses", id] });
      qc.invalidateQueries({ queryKey: ["theses"] });
    },
  });
}

export function useUpdateThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Thesis> }) =>
      updateThesis(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["theses", id] });
      qc.invalidateQueries({ queryKey: ["theses"] });
    },
  });
}
