import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

/** Reasoning-effort ladder, cheapest first (schema.d.ts `EffortEnum`). */
export type Effort = "low" | "medium" | "high" | "xhigh" | "max";

export type TradingProfile = {
  id: number;
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  /** Expose the default Toolset to the run. Non-Claude providers ALSO need
   *  ProviderConfig.supports_tools (Settings → Providers) or this is inert. */
  enable_tools: boolean;
  /** Claude-only. */
  enable_thinking: boolean;
  /** Only the budget-shaped Claude models read this; adaptive rows take `effort`. */
  thinking_budget: number;
  effort: Effort;
  /** Claude-only. */
  enable_memory: boolean;
  enable_coach: boolean;
  active: boolean;
};

export const fetchProfiles = () => apiGet<TradingProfile[]>("/api/profiles/");
export const fetchProfile = (id: number) => apiGet<TradingProfile>(`/api/profiles/${id}/`);
export const createProfile = (body: Partial<TradingProfile>) =>
  apiPost<TradingProfile>("/api/profiles/", body);
export const updateProfile = (id: number, body: Partial<TradingProfile>) =>
  apiPatch<TradingProfile>(`/api/profiles/${id}/`, body);
export const deleteProfile = (id: number) => apiDelete(`/api/profiles/${id}/`);

/** One file Claude's Memory tool wrote under this profile. */
export type MemoryEntry = {
  /** Path relative to the profile's memory directory. */
  path: string;
  size_bytes: number;
  modified_at: string;
  /** First `preview_chars` characters of the file. */
  preview: string;
  preview_truncated: boolean;
};

/** Everything stored under the profile's memory directory. */
export type ProfileMemory = {
  profile: number;
  /** False when the profile has never run with memory on. */
  exists: boolean;
  entries: MemoryEntry[];
  total_files: number;
  total_bytes: number;
  preview_chars: number;
};

export type ProfileMemoryCleared = {
  profile: number;
  removed_files: number;
  removed_bytes: number;
};

export const fetchProfileMemory = (id: number) =>
  apiGet<ProfileMemory>(`/api/profiles/${id}/memory/`);

/** Wipes the store. The model loses that context permanently. */
export const clearProfileMemory = (id: number) =>
  apiDelete<ProfileMemoryCleared>(`/api/profiles/${id}/memory/`);
