/**
 * Single home for the 16 user-toggleable snapshot section kinds (`vix` is
 * always-on and deliberately excluded — see VIX_LABEL below).
 *
 * Order is a parity contract with the backend's section-kind roster
 * (backend/apps/snapshots/models.py::SnapshotSection.KIND_CHOICES minus
 * `vix`, reordered to group the profile-default eight first). Labels mirror
 * backend/apps/snapshots/serializer.py::_title verbatim (its `.get(kind,
 * kind.title())` fallback is why `macro` reads "Macro" rather than "Macro
 * (FRED)") so the picker never drifts from what the AI actually sees
 * rendered in the payload.
 */

export const SECTION_KINDS = [
  "quotes",
  "ohlc",
  "chain",
  "positions",
  "breadth",
  "news",
  "events",
  "macro",
  "fundamentals",
  "filings",
  "treasury",
  "overnight",
  "image",
  "notes",
  "fed",
  "flowlite",
] as const;

export type SectionKind = (typeof SECTION_KINDS)[number];

export const SECTION_LABELS: Record<SectionKind, string> = {
  quotes: "Quotes",
  ohlc: "OHLC",
  chain: "Option chain",
  positions: "Positions",
  breadth: "Market breadth",
  news: "News",
  events: "Upcoming events",
  macro: "Macro",
  fundamentals: "Company fundamentals",
  filings: "SEC filings",
  treasury: "Treasury",
  overnight: "Overnight board",
  image: "Chart image",
  notes: "Notes",
  fed: "Fed communication",
  flowlite: "Flow proxy (volume-based)",
};

/** `vix` is never user-selectable — every capture path appends it to `includes`. */
export const VIX_LABEL = "VIX term structure";
