import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listSchedules, createSchedule, patchSchedule,
  deleteSchedule, runScheduleNow, CreateScheduleBody,
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
