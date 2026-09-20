import { ApiError, apiGet, apiPatch, apiPost } from "./client";

export type ProviderId = "claude" | "openai" | "local";
export const PROVIDER_IDS: readonly ProviderId[] = ["claude", "openai", "local"];
export const PROVIDER_LABEL: Record<ProviderId, string> = { claude: "Claude", openai: "OpenAI", local: "Local" };

/** Display name for a provider id; unknown ids render verbatim. */
export const providerLabel = (p: string): string => PROVIDER_LABEL[p as ProviderId] ?? p;

export type AiModel = {
  id: string; name: string; provider: string;
  input_per_mtok: number; output_per_mtok: number; cached_per_mtok: number;
  context_window: number; supports_vision: boolean;
  /** Snapshot payload budget the serializer targets for this model. */
  max_payload_tokens?: number;
};

/** `/api/schwab/models/`: the catalog plus the backend's per-provider fallback model. */
export type AiModelsResponse = {
  models: AiModel[];
  defaults?: Partial<Record<ProviderId, string>>;
};

export type ProviderConfig = {
  provider: ProviderId;
  base_url: string;
  default_model: string;
  enabled: boolean;
  supports_vision: boolean;
  supports_tools?: boolean;
  daily_cost_cap_usd: string;
  monthly_cost_cap_usd: string | null;
  api_key_present: boolean;
  discovered_models?: string[];
  models_synced_at?: string | null;
};

export const fetchAiModels = (provider?: string) => {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return apiGet<AiModelsResponse>(`/api/schwab/models/${query}`);
};

export const fetchProviderConfigs = () =>
  apiGet<ProviderConfig[]>("/api/schwab/providers/");

export const upsertProviderConfig = async (
  provider: string,
  body: Partial<ProviderConfig> & { api_key_write?: string },
) => {
  try {
    return await apiPatch<ProviderConfig>(`/api/schwab/providers/${provider}/`, body);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return apiPost<ProviderConfig>("/api/schwab/providers/", { provider, ...body });
    }
    throw err;
  }
};

export type ProbeResult = {
  ok: boolean;
  models?: string[];
  synced_at?: string | null;
  error?: string;
};

export const probeProvider = (
  provider: string,
  body: { base_url?: string; api_key_write?: string },
) => apiPost<ProbeResult>(`/api/schwab/providers/${provider}/probe/`, body);

export const fetchAiUsage = () => apiGet<{ today: Record<string, string> }>("/api/schwab/usage/");
