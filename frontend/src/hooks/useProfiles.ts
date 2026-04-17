import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  TradingProfile, createProfile, deleteProfile, fetchProfiles, updateProfile,
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
