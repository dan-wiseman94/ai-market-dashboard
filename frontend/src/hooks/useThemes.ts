import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createTheme, deleteTheme, fetchThemeHealth, fetchThemes } from "@/api/themes";

export const useThemes = () => useQuery({ queryKey: ["themes"], queryFn: fetchThemes });

export const useThemeHealth = (id: number | null, windowDays = 20) =>
  useQuery({
    queryKey: ["theme-health", id, windowDays],
    queryFn: () => fetchThemeHealth(id as number, windowDays),
    enabled: id != null,
  });

export function useCreateTheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createTheme,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["themes"] }),
  });
}

export function useDeleteTheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteTheme,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["themes"] }),
  });
}
