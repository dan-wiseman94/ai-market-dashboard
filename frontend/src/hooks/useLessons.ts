import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createLesson,
  deleteLesson,
  fetchLessons,
  updateLesson,
  type LessonFilters,
  type LessonWrite,
} from "@/api/lessons";

/** Every lessons query hangs off this root so one invalidate covers all filters. */
const ROOT = ["lessons"] as const;

export const useLessons = (filters: LessonFilters = {}) =>
  useQuery({
    queryKey: [...ROOT, filters],
    queryFn: () => fetchLessons(filters),
  });

export function useCreateLesson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LessonWrite) => createLesson(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }),
  });
}

export function useUpdateLesson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<LessonWrite> }) =>
      updateLesson(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }),
  });
}

export function useDeleteLesson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteLesson(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }),
  });
}
