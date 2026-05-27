import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import QuoteCell from "@/components/QuoteCell";
import type { Quote } from "@/api/market";

function makeQuote(overrides: Partial<Quote> = {}): Quote {
  return {
    last: 150.0,
    pct_change: 0,
    bid: null,
    ask: null,
    volume: null,
    high: null,
    low: null,
    ...overrides,
  };
}

describe("QuoteCell", () => {
  it("renders em-dash when q is undefined", () => {
    render(<QuoteCell q={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders em-dash when q.last is null", () => {
    render(<QuoteCell q={makeQuote({ last: null as unknown as number })} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders last value with 2 decimals", () => {
    render(<QuoteCell q={makeQuote({ last: 123.456, pct_change: null })} />);
    expect(screen.getByText("123.46")).toBeInTheDocument();
  });

  it("shows positive pct_change with + prefix and emerald color", () => {
    const { container } = render(
      <QuoteCell q={makeQuote({ last: 100, pct_change: 1.23 })} />,
    );
    expect(screen.getByText("+1.23%")).toBeInTheDocument();
    // light-mode base is emerald-700, with dark:text-emerald-400 for dark theme
    const pctSpan = container.querySelector(".text-emerald-700");
    expect(pctSpan).not.toBeNull();
  });

  it("shows negative pct_change with - prefix and rose color", () => {
    const { container } = render(
      <QuoteCell q={makeQuote({ last: 100, pct_change: -2.34 })} />,
    );
    expect(screen.getByText("-2.34%")).toBeInTheDocument();
    // light-mode base is rose-700, with dark:text-rose-400 for dark theme
    const pctSpan = container.querySelector(".text-rose-700");
    expect(pctSpan).not.toBeNull();
  });

  it("renders only last value when pct_change is null", () => {
    render(<QuoteCell q={makeQuote({ last: 42.0, pct_change: null })} />);
    expect(screen.getByText("42.00")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});
