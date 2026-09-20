import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type TradingProfile = {
  id: number;
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  active: boolean;
  // Per-profile AI platform features. Tool use on OpenAI/Local also depends on that
  // provider's own supports_tools; thinking and memory are Claude-only.
  enable_tools: boolean;
  enable_thinking: boolean;
  thinking_budget: number;
  enable_memory: boolean;
  enable_coach: boolean;
};

export const fetchProfiles = () => apiGet<TradingProfile[]>("/api/profiles/");
export const fetchProfile = (id: number) => apiGet<TradingProfile>(`/api/profiles/${id}/`);
export const createProfile = (body: Partial<TradingProfile>) =>
  apiPost<TradingProfile>("/api/profiles/", body);
export const updateProfile = (id: number, body: Partial<TradingProfile>) =>
  apiPatch<TradingProfile>(`/api/profiles/${id}/`, body);
export const deleteProfile = (id: number) => apiDelete(`/api/profiles/${id}/`);
