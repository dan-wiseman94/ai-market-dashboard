import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Citation } from "../components/Citation";

describe("Citation", () => {
  it("renders a numbered superscript by default", () => {
    render(
      <Citation
        index={1}
        source="https://example.com/a"
        title="FOMC holds"
        snippet="No change."
      />,
    );
    expect(screen.getByText("[1]")).toBeInTheDocument();
  });

  it("shows the title in the aria-label / title", () => {
    render(
      <Citation index={2} source="news://7" title="Tesla delivers" snippet="..." />,
    );
    const el = screen.getByText("[2]");
    expect(el.getAttribute("aria-label") || "").toContain("Tesla delivers");
  });

  it("wraps in an anchor tag for http sources", () => {
    const { container } = render(
      <Citation index={3} source="https://x/y" title="t" />,
    );
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a?.getAttribute("href")).toBe("https://x/y");
  });

  it("does not wrap news:// pseudo-uris in an anchor", () => {
    const { container } = render(
      <Citation index={4} source="news://42" title="t" />,
    );
    expect(container.querySelector("a")).toBeNull();
  });
});
