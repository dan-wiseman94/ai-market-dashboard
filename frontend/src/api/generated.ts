/**
 * Generated API types — incremental adoption surface.
 *
 * `schema.d.ts` is generated from `backend/schema.yml` (drf-spectacular) by
 * `pnpm gen:api` and drift-gated in CI, so it always mirrors the live backend
 * contract. The hand-written interfaces in the sibling modules (threads.ts,
 * thesis.ts, …) are migrated onto these generated shapes incrementally — starting
 * with the `*_id` contract surface, where a hand/back drift silently reads
 * `undefined`. Import generated response/request shapes from here.
 *
 * Deliberately retained though not yet imported — knip-ignored in knip.json as an
 * adoption anchor, not dead code. Delete only if the migration plan is abandoned.
 */
import type { components, paths } from "./schema";

/**
 * All component schemas, keyed by drf-spectacular's serializer-derived names.
 * @public — adoption surface (see module header); not yet consumed while interfaces migrate.
 */
export type Schemas = components["schemas"];

/**
 * Operation paths (method → params/requestBody/responses).
 * @public — adoption surface (see module header).
 */
export type ApiPaths = paths;
