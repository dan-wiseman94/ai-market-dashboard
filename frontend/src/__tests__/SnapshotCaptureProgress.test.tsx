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

  it("renders each section name", () => {
    const sections = new Map([
      ["quotes", "done" as const],
      ["chain", "running" as const],
    ]);
    render(<SnapshotCaptureProgress sections={sections} />);
    expect(screen.getByText(/quotes/i)).toBeInTheDocument();
    expect(screen.getByText(/chain/i)).toBeInTheDocument();
  });

  it("shows checkmark for done sections", () => {
    const sections = new Map([["quotes", "done" as const]]);
    render(<SnapshotCaptureProgress sections={sections} />);
    // The done icon must be visible alongside the section name
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("✓");
    expect(item).toHaveTextContent("quotes");
  });

  it("shows spinner/clock for running sections", () => {
    const sections = new Map([["chain", "running" as const]]);
    render(<SnapshotCaptureProgress sections={sections} />);
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("⏳");
    expect(item).toHaveTextContent("chain");
  });

  it("shows X for failed sections", () => {
    const sections = new Map([["news", "failed" as const]]);
    render(<SnapshotCaptureProgress sections={sections} />);
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("✗");
    expect(item).toHaveTextContent("news");
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
    // Each item must contain both the section name and the matching icon
    const texts = items.map((li) => li.textContent ?? "");
    expect(texts.some((t) => t.includes("quotes") && t.includes("✓"))).toBe(true);
    expect(texts.some((t) => t.includes("chain") && t.includes("⏳"))).toBe(true);
    expect(texts.some((t) => t.includes("news") && t.includes("✗"))).toBe(true);
  });

  it("has an accessible label for the progress list", () => {
    const sections = new Map([["quotes", "done" as const]]);
    render(<SnapshotCaptureProgress sections={sections} />);
    // The list should be labelled so screen readers understand the context
    expect(screen.getByRole("list", { name: /capture progress/i })).toBeInTheDocument();
  });
});
