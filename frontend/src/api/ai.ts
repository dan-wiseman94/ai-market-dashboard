import { apiGet, apiPatch, apiPost } from "./client";

export type AiModel = {
  id: string; name: string; provider: string;
  input_per_mtok: number; output_per_mtok: number; cached_per_mtok: number;
  context_window: number; supports_vision: boolean;
};

export type ProviderConfig = {
  provider: "claude" | "openai" | "local";
  base_url: string;
  default_model: string;
  enabled: boolean;
  supports_vision: boolean;
  daily_cost_cap_usd: string;
  api_key_present: boolean;
};

export const fetchAiModels = (provider?: string) =>
  apiGet<{ models: AiModel[] }>(`/api/schwab/models/${provider ? `?provider=${provider}` : ""}`);

export const fetchProviderConfigs = () =>
  apiGet<ProviderConfig[]>("/api/schwab/providers/");

export const upsertProviderConfig = (provider: string, body: Partial<ProviderConfig> & { api_key_write?: string }) => {
  return apiPatch<ProviderConfig>(`/api/schwab/providers/${provider}/`, body).catch(async (err) => {
    if ((err as { status?: number }).status === 404) {
      return apiPost<ProviderConfig>("/api/schwab/providers/", { provider, ...body });
    }
    throw err;
  });
};

export const fetchAiUsage = () => apiGet<{ today: Record<string, string> }>("/api/schwab/usage/");
