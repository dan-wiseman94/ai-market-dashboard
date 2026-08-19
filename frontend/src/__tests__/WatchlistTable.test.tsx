import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useQuotes } from "@/hooks/useQuotes";
import WatchlistTable from "@/components/WatchlistTable";
import type { WatchlistSymbol } from "@/api/watchlists";
import type { Quote } from "@/api/market";

vi.mock("@/hooks/useQuotes", () => ({
  useQuotes: vi.fn(),
}));

// QuoteCell is rendered directly — no additional mock needed.

const mockUseQuotes = vi.mocked(useQuotes);

const symbols: WatchlistSymbol[] = [
  { id: 1, ticker: "AAPL", sort_order: 0 },
  { id: 2, ticker: "TSLA", sort_order: 1 },
];

function makeQuote(overrides: Partial<Quote> = {}): Quote {
  return {
    last: 150.0,
    bid: 149.9,
    ask: 150.1,
    volume: 1000000,
    high: null,
    low: null,
    pct_change: 0.5,
    ...overrides,
  };
}

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

beforeEach(() => {
  mockUseQuotes.mockReturnValue({ data: undefined } as ReturnType<typeof useQuotes>);
});

describe("WatchlistTable", () => {
  it("renders table headers even when symbols is empty", () => {
    render(wrap(<WatchlistTable symbols={[]} />));
    expect(screen.getByText("Ticker")).toBeInTheDocument();
    expect(screen.getByText("Last")).toBeInTheDocument();
    expect(screen.getByText("Bid")).toBeInTheDocument();
    expect(screen.getByText("Ask")).toBeInTheDocument();
    expect(screen.getByText("Vol")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders one row per symbol with ticker link to /market/<ticker>", () => {
    render(wrap(<WatchlistTable symbols={symbols} />));
    const aaplLink = screen.getByRole("link", { name: "AAPL" });
    const tslaLink = screen.getByRole("link", { name: "TSLA" });
    expect(aaplLink).toHaveAttribute("href", "/market/AAPL");
    expect(tslaLink).toHaveAttribute("href", "/market/TSLA");
  });

  it("renders bid, ask, volume from quotes data; shows em-dash when null", () => {
    const quotes: Record<string, Quote> = {
      AAPL: makeQuote({ bid: 149.9, ask: 150.1, volume: 1234567 }),
      TSLA: makeQuote({ bid: null, ask: null, volume: null }),
    };
    mockUseQuotes.mockReturnValue({ data: quotes } as ReturnType<typeof useQuotes>);
    render(wrap(<WatchlistTable symbols={symbols} />));
    expect(screen.getByText("149.90")).toBeInTheDocument();
    expect(screen.getByText("150.10")).toBeInTheDocument();
    expect(screen.getByText("1,234,567")).toBeInTheDocument();
    // TSLA has null bid/ask/volume — each shows em-dash
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("Remove button is hidden when onRemove is not provided", () => {
    render(wrap(<WatchlistTable symbols={symbols} />));
    expect(screen.queryByRole("button", { name: /Remove/i })).not.toBeInTheDocument();
  });

  it("Remove button is shown and calls onRemove(symbolId) when clicked", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(wrap(<WatchlistTable symbols={symbols} onRemove={onRemove} />));
    const removeButtons = screen.getAllByRole("button", { name: /Remove/i });
    expect(removeButtons.length).toBe(2);
    await user.click(removeButtons[0]);
    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(onRemove).toHaveBeenCalledWith(1); // symbols[0].id
  });
});
