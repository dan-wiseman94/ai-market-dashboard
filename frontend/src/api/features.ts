import { apiGet, apiPatch } from "./client";

/**
 * `GET /api/features/` — the whole Features page in one read.
 *
 * The endpoint is read-only. Every write goes back to the endpoint that already owns
 * the row, named per row by `write_path` (`/api/settings/` for the global knobs,
 * `/api/briefings/config/` for the briefing singleton). That keeps the existing
 * server-side validation as the only path into those columns.
 *
 * The payload arrives as four typed arrays rather than one polymorphic list so that
 * `value` stays concrete; `flattenFeatures` joins them into a discriminated union.
 */

export type FeatureSource = "override" | "env" | "default";

export interface FeatureRequirement {
  id: string;
  label: string;
  /** null = the probe itself failed. Render "unknown", never "not connected". */
  satisfied: boolean | null;
  manage_path: string;
}

export interface FeatureGroupMeta {
  key: string;
  label: string;
  blurb: string;
  order: number;
}

export interface FeatureChoice {
  value: string;
  label: string;
}

interface FeatureRowBase {
  key: string;
  label: string;
  summary: string;
  help: string;
  group: string;
  order: number;
  scope: string;
  backing: string;
  value_type: string;
  editable: boolean;
  /** Empty when the row is not writable from here. */
  write_path: string;
  /** The field name to send in the PATCH body. */
  field: string;
  env_var: string;
  env_only_reason: string;
  costs_money: boolean;
  cost_note: string;
  retroactive: boolean;
  requires: string[];
  requirement: FeatureRequirement | null;
  provider_only: string;
  deep_link: string;
}

export interface FeatureToggle extends FeatureRowBase {
  value: boolean;
  /** What "reset to default" actually restores — the env-or-shipped value. */
  default_value: boolean;
  shipped_default: boolean | null;
  override: boolean | null;
  source: FeatureSource;
}

export interface FeatureNumber extends FeatureRowBase {
  value: number;
  default_value: number;
  shipped_default: number | null;
  override: number | null;
  source: FeatureSource;
  min_value: number | null;
  max_value: number | null;
  unit: string;
  is_float: boolean;
}

export interface FeatureText extends FeatureRowBase {
  value: string;
  default_value: string;
  shipped_default: string | null;
  override: string | null;
  source: FeatureSource;
  choices: FeatureChoice[];
  max_length: number;
}

export interface PerObjectFeature extends FeatureRowBase {
  /** null for a non-boolean field, and for a degraded read. Never coerce to 0. */
  on: number | null;
  total: number | null;
  degraded: boolean;
  noun: string;
}

export interface FeatureRegistry {
  groups: FeatureGroupMeta[];
  toggles: FeatureToggle[];
  numbers: FeatureNumber[];
  texts: FeatureText[];
  per_object: PerObjectFeature[];
}

export type FeatureItem =
  | ({ kind: "toggle" } & FeatureToggle)
  | ({ kind: "number" } & FeatureNumber)
  | ({ kind: "text" } & FeatureText)
  | ({ kind: "per_object" } & PerObjectFeature);

export type FeatureValue = boolean | number | string | null;

/** One ordered list, sorted by group then by the row's declared order. */
export function flattenFeatures(reg: FeatureRegistry): FeatureItem[] {
  const groupOrder = new Map(reg.groups.map((g) => [g.key, g.order]));
  const items: FeatureItem[] = [
    ...reg.toggles.map((r): FeatureItem => ({ kind: "toggle", ...r })),
    ...reg.numbers.map((r): FeatureItem => ({ kind: "number", ...r })),
    ...reg.texts.map((r): FeatureItem => ({ kind: "text", ...r })),
    ...reg.per_object.map((r): FeatureItem => ({ kind: "per_object", ...r })),
  ];
  return items.sort((a, b) => {
    const ga = groupOrder.get(a.group) ?? 99;
    const gb = groupOrder.get(b.group) ?? 99;
    return ga - gb || a.order - b.order || a.key.localeCompare(b.key);
  });
}

export const fetchFeatures = () => apiGet<FeatureRegistry>("/api/features/");

/**
 * Write one row through the endpoint the payload names. `null` clears an override so
 * the value inherits its default again.
 */
export const saveFeatureValue = (
  writePath: string,
  field: string,
  value: FeatureValue,
): Promise<Record<string, unknown>> =>
  apiPatch<Record<string, unknown>>(writePath, { [field]: value });
