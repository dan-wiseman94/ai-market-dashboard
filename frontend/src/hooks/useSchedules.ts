import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listSchedules, createSchedule, patchSchedule,
  deleteSchedule, runScheduleNow, CreateScheduleBody, UpdateScheduleBody,
} from "@/api/observer";

export function useSchedules() {
  return useQuery({ queryKey: ["schedules"], queryFn: listSchedules });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateScheduleBody) => createSchedule(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useToggleSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patchSchedule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

/**
 * Full-schedule edit. `market_hours_only`, `mode`, `structured`, `use_batch`,
 * `consensus`, `fire_mode` and `close_offset_minutes` are all writable after
 * create — the ViewSet's `perform_update` re-syncs the PeriodicTask.
 */
export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UpdateScheduleBody }) =>
      patchSchedule(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useUpdateScheduleIncludes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, default_includes }: { id: number; default_includes: string[] }) =>
      patchSchedule(id, { default_includes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useRunSchedule() {
  return useMutation({ mutationFn: (id: number) => runScheduleNow(id) });
}
