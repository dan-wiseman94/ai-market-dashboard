import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listCalendarOverrides,
  createCalendarOverride,
  deleteCalendarOverride,
} from "@/api/market";

const KEY = ["calendar-overrides"];

export function useCalendarOverrides() {
  return useQuery({ queryKey: KEY, queryFn: listCalendarOverrides });
}

export function useCreateCalendarOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createCalendarOverride,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteCalendarOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteCalendarOverride,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
