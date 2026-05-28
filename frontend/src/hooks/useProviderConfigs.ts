import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProviderConfigs, probeProvider, upsertProviderConfig } from "@/api/ai";

export const useProviderConfigs = () =>
  useQuery({ queryKey: ["provider-configs"], queryFn: fetchProviderConfigs });

export function useUpsertProviderConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }: { provider: string; body: Parameters<typeof upsertProviderConfig>[1] }) =>
      upsertProviderConfig(provider, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-configs"] });
      qc.invalidateQueries({ queryKey: ["ai-usage"] });
      qc.invalidateQueries({ queryKey: ["costs-caps"] });
    },
  });
}

export function useProbeProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      provider,
      body,
    }: {
      provider: string;
      body: { base_url?: string; api_key_write?: string };
    }) => probeProvider(provider, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-configs"] });
    },
  });
}
