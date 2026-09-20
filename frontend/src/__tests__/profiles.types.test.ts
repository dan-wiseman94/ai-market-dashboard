import { describe, it, expect } from "vitest";
import { BLANK_DRAFT, SECTION_OPTIONS } from "@/pages/profiles/types";

// Literal parity list from the task brief — every backend SnapshotSection kind
// except `vix` (always-on, never user-selectable; see snapshotSections.ts).
const ALL_KINDS = [
  "quotes", "ohlc", "chain", "positions", "breadth", "news", "events", "macro",
  "fundamentals", "filings", "treasury", "overnight", "image", "notes", "fed", "flowlite",
];

describe("SECTION_OPTIONS", () => {
  it("covers every backend section kind except vix, in order", () => {
    expect([...SECTION_OPTIONS]).toEqual(ALL_KINDS);
  });
});

describe("BLANK_DRAFT", () => {
  it("seeds new profiles with the backend's rich eight-kind default_includes", () => {
    // Mirrors TradingProfile.DEFAULT_INCLUDES (backend/apps/profiles/models.py).
    expect(BLANK_DRAFT.default_includes).toEqual([
      "quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro",
    ]);
  });
});
