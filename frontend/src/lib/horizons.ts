/**
 * Post-mortem horizon set. The backend setting THESIS_POSTMORTEM_HORIZONS is
 * the source of truth; the calibration-family analytics payloads carry it as
 * a `horizons` field. These literals only seed the horizon pickers before the
 * first payload arrives.
 */

export const FALLBACK_HORIZONS: readonly number[] = [7, 30, 90];

/** Horizons from an analytics payload, falling back before the fetch lands.
 * Accepts `unknown` so callers whose payload interface predates the
 * `horizons` field still typecheck. */
export function horizonsFrom(payload: unknown): readonly number[] {
  const h =
    payload && typeof payload === "object"
      ? (payload as { horizons?: unknown }).horizons
      : undefined;
  return Array.isArray(h) && h.length > 0 && h.every((x) => typeof x === "number")
    ? (h as number[])
    : FALLBACK_HORIZONS;
}
