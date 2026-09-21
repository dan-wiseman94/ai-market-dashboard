import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Citation, httpHref } from "../components/Citation";

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

  // `news://<id>` is the EXTERNAL feed's id, not a NewsItem pk, and nothing
  // resolves it — so there is no target to link to, ever.
  it("does not wrap an unresolvable news:// pseudo-uri in an anchor", () => {
    const { container } = render(
      <Citation index={4} source="news://42" title="t" />,
    );
    expect(container.querySelector("a")).toBeNull();
  });

  it("renders a document citation (no source) as a bare marker", () => {
    const { container } = render(
      <Citation index={5} source="" title="10-K.pdf" snippet="Revenue grew" />,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText("[5]").getAttribute("aria-label")).toBe("10-K.pdf: Revenue grew");
  });
});

describe("httpHref — model-influenced source hardening", () => {
  it.each([
    ["https://example.com/a", "https://example.com/a"],
    ["http://example.com/a", "http://example.com/a"],
  ])("accepts the real web scheme %s", (source, expected) => {
    expect(httpHref(source)).toBe(expected);
  });

  // A prefix test ("starts with http") accepts every one of these.
  it.each([
    "httpevil://example.com/pwn",
    "https-evil://example.com",
    "httpx:payload",
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "news://4821",
    "vbscript:msgbox(1)",
    "",
    "   ",
    "//example.com/protocol-relative",
    "/relative/path",
  ])("rejects %s", (source) => {
    expect(httpHref(source)).toBeNull();
  });

  it("does not render a link for a javascript: source", () => {
    const { container } = render(
      <Citation index={9} source="javascript:alert(1)" title="xss" />,
    );
    expect(container.querySelector("a")).toBeNull();
  });
});
