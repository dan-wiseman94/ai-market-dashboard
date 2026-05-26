import { apiGet, apiPost } from "./client";

export type JournalDecision = "acted" | "passed" | "watching" | "hedged";

export interface JournalEntry {
  id: number;
  thread_id: number;
  thesis_id: number | null;
  snapshot_id: number | null;
  decision: JournalDecision;
  note: string;
  created_at: string;
}

export interface CreateJournalBody {
  thread_id: number;
  decision: JournalDecision;
  note?: string;
  thesis_id?: number;
  snapshot_id?: number;
}

export const listJournal = (threadId: number) =>
  apiGet<JournalEntry[]>(`/api/journal/?thread=${threadId}`);

export const createJournalEntry = (body: CreateJournalBody) =>
  apiPost<JournalEntry>("/api/journal/", body);
