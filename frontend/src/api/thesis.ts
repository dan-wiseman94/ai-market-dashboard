import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type ThesisDirection = "bullish" | "bearish" | "neutral";
export type ThesisStatus =
  | "open"
  | "closed_win"
  | "closed_loss"
  | "closed_scratch"
  | "invalidated";

export interface Thesis {
  id: number;
  title: string;
  ticker: string;
  direction: ThesisDirection;
  rationale: string;
  conviction: number;
  entry_price: string | null;
  target_price: string | null;
  invalidation_price: string | null;
  horizon_days: number | null;
  status: ThesisStatus;
  profile: number | null;
  thread: number | null;
  snapshot: number | null;
  review_thread: number | null;
  opened_at: string;
  closed_at: string | null;
  close_note: string;
  created_at: string;
  updated_at: string;
}

export interface CreateThesisBody {
  title: string;
  ticker: string;
  direction: ThesisDirection;
  rationale?: string;
  conviction?: number;
  entry_price?: string | null;
  target_price?: string | null;
  invalidation_price?: string | null;
  horizon_days?: number | null;
  profile?: number | null;
  thread_id?: number | null;
  snapshot_id?: number | null;
}

export interface CloseThesisBody {
  status: Exclude<ThesisStatus, "open">;
  close_note?: string;
}

export const listTheses = () => apiGet<Thesis[]>("/api/theses/");
export const getThesis = (id: number) => apiGet<Thesis>(`/api/theses/${id}/`);
export const createThesis = (body: CreateThesisBody) =>
  apiPost<Thesis>("/api/theses/", body);
export const patchThesis = (id: number, body: Partial<CreateThesisBody>) =>
  apiPatch<Thesis>(`/api/theses/${id}/`, body);
export const closeThesis = (id: number, body: CloseThesisBody) =>
  apiPost<Thesis>(`/api/theses/${id}/close/`, body);
export const deleteThesis = (id: number) => apiDelete(`/api/theses/${id}/`);
