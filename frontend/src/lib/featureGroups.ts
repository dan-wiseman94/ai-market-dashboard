/**
 * Presentation-only companions to the Features registry.
 *
 * Everything a user reads about a *feature* — label, summary, help, cost note, the
 * reason a row is read-only — is served by `GET /api/features/` and rendered
 * verbatim, exactly as `lib/snapshotSections.ts` mirrors its backend roster. This
 * file holds only what has no business living in Python: where a deep link points in
 * the SPA, badge wording, and the filter chips. It contains no feature keys.
 */

import type { FeatureItem } from "@/api/features";

/** Human name for a deep-link target, so a link can say where it goes. */
export const DEEP_LINK_LABELS: Record<string, string> = {
  "/profiles": "Profiles",
  "/schedules": "Schedules",
  "/triggers": "Triggers",
  "/briefing": "Briefing",
  "/theses": "Theses",
  "/snapshot": "Snapshot composer",
  "/settings": "AI Providers",
  "/settings/connections": "Connections",
};

export function deepLinkLabel(path: string): string {
  return DEEP_LINK_LABELS[path] ?? path;
}

export const BADGE_MONEY = "Spends AI $";
export const BADGE_RETROACTIVE = "Retroactive";
export const BADGE_ENV_ONLY = "Environment only";
export const BADGE_ALWAYS_ON = "Always on";

/** Provenance chip wording. `default` stays quiet — it is the uninteresting case. */
export const SOURCE_LABELS: Record<string, string> = {
  override: "Overridden",
  env: "From .env",
  default: "Default",
};

/**
 * Shown before arming anything that bills a provider. Turning something OFF is always
 * free and never asks.
 */
export function moneyConfirm(label: string, costNote: string): string {
  return `"${label}" spends money when it runs.\n\n${costNote}\n\nTurn it on?`;
}

/**
 * The retroactive warning, worded for the one methodology switch: flipping it does
 * not recompute anything, it changes how every already-recorded number is derived.
 */
export function retroactiveConfirm(label: string): string {
  return (
    `"${label}" is retroactive.\n\n` +
    "Every post-mortem, Scorecard and Mirror number already computed under " +
    "price-return will be restated. Nothing is recalculated and stored — the " +
    "recorded history simply reads differently from now on.\n\nTurn it on?"
  );
}

export type FilterId = "all" | "on" | "off" | "overridden" | "money";

export const FILTERS: Array<{ id: FilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "on", label: "On" },
  { id: "off", label: "Off" },
  { id: "overridden", label: "Overridden" },
  { id: "money", label: "Spends money" },
];

function isOn(item: FeatureItem): boolean | null {
  if (item.kind === "toggle") return item.value;
  if (item.kind === "per_object") return item.on === null ? null : item.on > 0;
  return null;
}

export function matchesFilter(item: FeatureItem, filter: FilterId): boolean {
  switch (filter) {
    case "on":
      return isOn(item) === true;
    case "off":
      return isOn(item) === false;
    case "overridden":
      return item.kind !== "per_object" && item.source === "override";
    case "money":
      return item.costs_money;
    default:
      return true;
  }
}

/** Free-text search across the copy the user can actually see. */
export function matchesQuery(item: FeatureItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [item.label, item.summary, item.help, item.env_var]
    .join(" ")
    .toLowerCase()
    .includes(q);
}
