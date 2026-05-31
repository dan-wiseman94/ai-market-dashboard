import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type ThesisDirection = "bullish" | "bearish" | "neutral";
export type ThesisStatus =
  | "open"
  | "closed_win"
  | "closed_loss"
  | "closed_scratch"
  | "invalidated";

export type PostMortemVerdict =
  | "correct"
  | "incorrect"
  | "mixed"
  | "inconclusive"
  | "";

export type PostMortemStatus =
  | "scheduled"
  | "running"
  | "done"
  | "failed"
  | "skipped";

export interface PostMortemReport {
  summary: string;
  what_worked: string[];
  what_missed: string[];
  lessons: string[];
  would_repeat: boolean;
  narrative_verdict: PostMortemVerdict;
}

export interface PostMortem {
  id: number;
  horizon_days: number;
  due_at: string;
  status: PostMortemStatus;
  forward_return_pct: number | null;
  verdict: PostMortemVerdict;
  report: PostMortemReport | Record<string, never>;
  message_id: number | null;
  created_at: string;
  completed_at: string | null;
}

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
  profile_id: number | null;
  thread_id: number | null;
  snapshot_id: number | null;
  review_thread_id: number | null;
  guard_enabled: boolean;
  guard_trigger_id: number | null;
  opened_at: string;
  closed_at: string | null;
  close_note: string;
  created_at: string;
  updated_at: string;
  postmortems: PostMortem[];
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
  invalidation_note?: string;
  horizon_days?: number | null;
  profile_id?: number | null;
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
export const updateThesis = (id: number, body: Partial<Thesis>) =>
  apiPatch<Thesis>(`/api/theses/${id}/`, body);
export const closeThesis = (id: number, body: CloseThesisBody) =>
  apiPost<Thesis>(`/api/theses/${id}/close/`, body);
export const deleteThesis = (id: number) => apiDelete(`/api/theses/${id}/`);
export const runPostmortem = (id: number) =>
  apiPost<{ postmortem_id?: number }>(`/api/theses/${id}/run-postmortem/`);
