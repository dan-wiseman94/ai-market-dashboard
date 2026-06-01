import { apiGet, apiPost } from "@/api/client";

export interface WarRoomMessage { role: string; content: Record<string, unknown> }
export interface WarRoomVerdict {
  verdict?: string; confidence?: number; strongest_bull?: string;
  strongest_bear?: string; what_would_change_my_mind?: string;
}
export interface WarRoomRun {
  id: number;
  created_at: string;
  subject_kind: string;
  subject_label: string;
  params: Record<string, unknown>;
  verdict: WarRoomVerdict;
  confidence: number | null;
  status: string;
  error: string;
  thread_id: number;
  messages: WarRoomMessage[];
}

export interface ConveneBody {
  free_prompt?: string;
  thesis_id?: number;
  coverage_note_id?: number;
  book_snapshot_id?: number;
  structure?: "judge_panel" | "rebuttal" | "deep";
  voice_mode?: "single" | "multi";
  grounding?: boolean;
}

export const fetchWarRoomRuns = () => apiGet<WarRoomRun[]>("/api/warroom/runs/");
export const fetchWarRoomRun = (id: number) => apiGet<WarRoomRun>(`/api/warroom/runs/${id}/`);
export const conveneWarRoom = (body: ConveneBody) => apiPost<WarRoomRun>("/api/warroom/runs/convene/", body);
