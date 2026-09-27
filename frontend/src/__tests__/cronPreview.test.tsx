import { describe, it, expect } from "vitest";
import { explainCron } from "../lib/cronPreview";

describe("cronPreview", () => {
  it("explains every 15 minutes correctly", () => {
    expect(explainCron("*/15 * * * *")).toMatch(/every 15 minutes/i);
  });

  it("returns an invalid string on bad input", () => {
    expect(explainCron("not a cron")).toMatch(/invalid/i);
  });
});
