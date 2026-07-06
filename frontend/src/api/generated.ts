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
 * Consumed by `api/threads.ts` (Message's `*_id` FK surface) — so backend
 * contract drift on adopted fields is caught at type-check time.
 */
import type { components } from "./schema";

/**
 * All component schemas, keyed by drf-spectacular's serializer-derived names.
 * @public — adoption surface (see module header).
 */
export type Schemas = components["schemas"];
