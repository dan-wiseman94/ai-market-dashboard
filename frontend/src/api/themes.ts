import { apiDelete, apiGet, apiPost } from "@/api/client";

export interface Theme {
  id: number;
  name: string;
  tickers: string[];
  note: string;
  created_at: string;
  updated_at: string;
}

export interface ThemeMember {
  ticker: string;
  return_pct: number | null;
  above_theme?: boolean;
}

export interface ThemeHealth {
  window_days: number;
  coverage: { priced: number; total: number };
  breadth: number | null;
  mean_return_pct: number | null;
  spx_return_pct: number | null;
  relative_strength: number | null;
  leadership: {
    leader: { ticker: string; return_pct: number };
    laggard: { ticker: string; return_pct: number };
  } | null;
  members: ThemeMember[];
}

export const fetchThemes = () => apiGet<Theme[]>("/api/themes/");
export const createTheme = (body: { name: string; tickers: string[]; note?: string }) =>
  apiPost<Theme>("/api/themes/", body);
export const deleteTheme = (id: number) => apiDelete(`/api/themes/${id}/`);
export const fetchThemeHealth = (id: number, windowDays = 20) =>
  apiGet<ThemeHealth>(`/api/themes/${id}/health/?window_days=${windowDays}`);
