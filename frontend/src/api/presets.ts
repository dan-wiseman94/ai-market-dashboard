import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type AgentPreset = {
  id: number;
  name: string;
  slug: string;
  description: string;
  objective_template: string;
  default_includes: string[];
  structured: boolean;
  builtin: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type CreatePresetBody = {
  name: string;
  description?: string;
  objective_template: string;
  default_includes: string[];
  structured?: boolean;
  active?: boolean;
};

export type UpdatePresetBody = Partial<CreatePresetBody>;

export const listPresets = () => apiGet<AgentPreset[]>("/api/presets/");
export const createPreset = (body: CreatePresetBody) =>
  apiPost<AgentPreset>("/api/presets/", body);
export const updatePreset = (id: number, body: UpdatePresetBody) =>
  apiPatch<AgentPreset>(`/api/presets/${id}/`, body);
export const deletePreset = (id: number) => apiDelete(`/api/presets/${id}/`);
