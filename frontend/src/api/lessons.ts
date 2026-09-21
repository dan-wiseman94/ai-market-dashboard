import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/client";

/** Mirrors `apps.thesis.lessons.MIN_LESSON_SUPPORT` — the number of post-mortems a
 * distilled lesson must recur across before the Coach will read it. A hand-written
 * lesson has no evidence rows, so its support_n stays 0 and only `pinned` makes it
 * visible. The server still owns the rule; this is copy, not logic. */
export const MIN_LESSON_SUPPORT = 2;

/** The directions the Coach matches on (`Thesis.DIRECTION_CHOICES`). */
export const LESSON_DIRECTIONS = ["bearish", "bullish", "neutral"] as const;
export type LessonDirection = (typeof LESSON_DIRECTIONS)[number];

/** The Coach's only matcher: a lesson surfaces when the situation's direction or
 * sector is tagged on it, so an untagged lesson is one that never appears. */
export interface LessonTags {
  directions?: string[];
  sectors?: string[];
}

export interface Lesson {
  id: number;
  text: string;
  tags: LessonTags;
  support_n: number;
  muted: boolean;
  pinned: boolean;
  /** The resolved coach-visibility rule, decided server-side. */
  visible_to_coach: boolean;
  last_seen: string | null;
  created_at: string;
  updated_at: string;
}

/** Tri-state list filters: omit a key to not filter on it at all. */
export interface LessonFilters {
  muted?: boolean;
  pinned?: boolean;
  visible?: boolean;
}

export interface LessonWrite {
  text: string;
  tags: LessonTags;
  muted?: boolean;
  pinned?: boolean;
}

export function lessonQueryString(filters: LessonFilters): string {
  const params = new URLSearchParams();
  for (const key of ["muted", "pinned", "visible"] as const) {
    const value = filters[key];
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const fetchLessons = (filters: LessonFilters = {}) =>
  apiGet<Lesson[]>(`/api/lessons/${lessonQueryString(filters)}`);

export const createLesson = (body: LessonWrite) => apiPost<Lesson>("/api/lessons/", body);

export const updateLesson = (id: number, body: Partial<LessonWrite>) =>
  apiPatch<Lesson>(`/api/lessons/${id}/`, body);

export const deleteLesson = (id: number) => apiDelete(`/api/lessons/${id}/`);
