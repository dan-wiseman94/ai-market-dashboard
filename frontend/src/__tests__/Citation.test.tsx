import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Citation, httpHref } from "../components/Citation";

describe("Citation", () => {

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
