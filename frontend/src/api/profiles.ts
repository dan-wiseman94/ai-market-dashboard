import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type TradingProfile = {
  id: number;
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
  active: boolean;
};

export const fetchProfiles = () => apiGet<TradingProfile[]>("/api/profiles/");
export const fetchProfile = (id: number) => apiGet<TradingProfile>(`/api/profiles/${id}/`);
export const createProfile = (body: Partial<TradingProfile>) =>
  apiPost<TradingProfile>("/api/profiles/", body);
export const updateProfile = (id: number, body: Partial<TradingProfile>) =>
  apiPatch<TradingProfile>(`/api/profiles/${id}/`, body);
export const deleteProfile = (id: number) => apiDelete(`/api/profiles/${id}/`);
