import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  TradingProfile, clearProfileMemory, createProfile, deleteProfile, fetchProfileMemory,
  fetchProfiles, updateProfile,
} from "@/api/profiles";

export const useProfiles = () =>
  useQuery({ queryKey: ["profiles"], queryFn: fetchProfiles });

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<TradingProfile>) => createProfile(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<TradingProfile> }) => updateProfile(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export const profileMemoryKey = (id: number) => ["profile-memory", id] as const;

/**
 * What Claude's Memory tool has stored for one profile. `id` is null while the
 * editor is creating a profile (no row, so no store yet) — the query stays idle.
 */
export const useProfileMemory = (id: number | null) =>
  useQuery({
    queryKey: profileMemoryKey(id ?? 0),
    queryFn: () => fetchProfileMemory(id ?? 0),
    enabled: id !== null,
  });

/** Wipes a profile's memory store. The model loses that context permanently. */
export function useClearProfileMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => clearProfileMemory(id),
    onSuccess: (_data, id) => qc.invalidateQueries({ queryKey: profileMemoryKey(id) }),
  });
}
