import { apiGet, apiPost } from "@/api/client";

export interface DeskAction { type: string; label: string; params?: Record<string, unknown> }
export interface DeskEntry {
  id: number;
  created_at: string;
  anomaly_type: string;
  ticker: string;
  severity: number;
  evidence: Record<string, unknown>;
  finding: string;
  suggested_actions: DeskAction[];
  status: "new" | "acted" | "dismissed";
  warroom_run_id: number | null;
  investigation_thread_id: number | null;
}

export const fetchDeskFeed = () => apiGet<DeskEntry[]>("/api/desk/");
export const runDeskSweep = () => apiPost<{ created: number }>("/api/desk/sweep/");
export const actDeskEntry = (id: number, actionType: string) =>
  apiPost<DeskEntry>(`/api/desk/${id}/act/`, { action: actionType });
export const dismissDeskEntry = (id: number) => apiPost<DeskEntry>(`/api/desk/${id}/dismiss/`);
