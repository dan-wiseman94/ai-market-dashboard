/**
 * TDD tests for SnapshotCaptureProgress component.
 *
 * Renders a per-section checklist based on a Map<section, SectionStatus>.
 * Icons: done → ✓, running → ⏳, failed → ✗
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SnapshotCaptureProgress } from "@/components/SnapshotCaptureProgress";

describe("SnapshotCaptureProgress", () => {
  it("renders nothing when sections map is empty", () => {
    const { container } = render(
      <SnapshotCaptureProgress sections={new Map()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders all three statuses in a multi-section map", () => {
    const sections = new Map([
      ["quotes", "done" as const],
      ["chain", "running" as const],
      ["news", "failed" as const],
    ]);
    render(<SnapshotCaptureProgress sections={sections} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    const texts = items.map((li) => li.textContent ?? "");
    expect(texts.some((t) => t.includes("quotes") && t.includes("✓"))).toBe(true);
    expect(texts.some((t) => t.includes("chain") && t.includes("⏳"))).toBe(true);
    expect(texts.some((t) => t.includes("news") && t.includes("✗"))).toBe(true);
  });

  it("has an accessible label for the progress list", () => {
    const sections = new Map([["quotes", "done" as const]]);
    render(<SnapshotCaptureProgress sections={sections} />);
    expect(screen.getByRole("list", { name: /capture progress/i })).toBeInTheDocument();
  });
});
