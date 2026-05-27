import { describe, it, expect } from "vitest";
import { sessionKind, SESSION_LABEL } from "@/lib/marketSession";

describe("sessionKind", () => {
  it("returns 'open' when the regular session is open", () => {
    expect(sessionKind({ is_open: true, phase: "open" })).toBe("open");
  });

  it("returns 'extended' for premarket", () => {
    expect(sessionKind({ is_open: false, phase: "premarket" })).toBe("extended");
  });

  it("returns 'extended' for postmarket", () => {
    expect(sessionKind({ is_open: false, phase: "postmarket" })).toBe("extended");
  });

  it("returns 'closed' for closed/weekend/holiday/half_day", () => {
    for (const phase of ["closed", "weekend", "holiday", "half_day"]) {
      expect(sessionKind({ is_open: false, phase })).toBe("closed");
    }
  });

  it("treats a missing phase as closed when not open", () => {
    expect(sessionKind({ is_open: false })).toBe("closed");
  });

  it("maps each kind to a human label", () => {
    expect(SESSION_LABEL.open).toBe("Open");
    expect(SESSION_LABEL.extended).toBe("Extended Hours");
    expect(SESSION_LABEL.closed).toBe("Closed");
  });
});
