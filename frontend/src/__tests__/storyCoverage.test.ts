/**
 * Story-coverage ratchet for high-value component dirs.
 *
 * The storybook lane only catches regressions in components that HAVE stories.
 * This guard prevents the story-less set from growing: if you add a high-value
 * component without a co-located *.stories.tsx (or delete a story), this fails.
 * As stories are added, lower STORYLESS_BASELINE — it only ratchets down.
 */
import { existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url)); // src/__tests__
const COMPONENTS_DIR = join(here, "..", "components");
const HIGH_VALUE_DIRS = ["", "settings", "triggers", "dashboard", "analytics", "costs"];

// Measured 35 on 2026-06-27 (24 stories added since the milestone began). Only
// ever lower this — raising it means a high-value component shipped story-less.
const STORYLESS_BASELINE = 35;

function storylessComponents(): string[] {
  const missing: string[] = [];
  for (const sub of HIGH_VALUE_DIRS) {
    const dir = join(COMPONENTS_DIR, sub);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      if (!f.endsWith(".tsx") || f.endsWith(".stories.tsx") || f.endsWith(".test.tsx")) continue;
      const story = join(dir, f.replace(/\.tsx$/, ".stories.tsx"));
      if (!existsSync(story)) missing.push(join(sub, f));
    }
  }
  return missing.sort();
}

describe("story coverage guard", () => {
  it("does not grow the story-less set in high-value dirs", () => {
    const missing = storylessComponents();
    expect(
      missing.length,
      `${missing.length} high-value components lack a story:\n  ${missing.join("\n  ")}\n` +
        "Add a co-located *.stories.tsx, or — if you added stories — lower STORYLESS_BASELINE.",
    ).toBeLessThanOrEqual(STORYLESS_BASELINE);
  });
});
