import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AgentPreset, CreatePresetBody, UpdatePresetBody,
  createPreset, deletePreset, listPresets, updatePreset,
} from "@/api/presets";

export const useAgentPresets = () =>
  useQuery({ queryKey: ["presets"], queryFn: listPresets });

export function useCreatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePresetBody) => createPreset(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

export function useUpdatePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UpdatePresetBody }) => updatePreset(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

export function useDeletePreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deletePreset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });
}

// Re-export type for convenience
export type { AgentPreset };
