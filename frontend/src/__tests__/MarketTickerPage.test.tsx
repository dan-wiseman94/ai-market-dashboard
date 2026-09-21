import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import MarketTickerPage from "../pages/MarketTickerPage";
import { mockFetch, renderWithProviders } from "./testUtils";

beforeEach(() => {
  mockFetch((url) => {
    if (url.includes("/api/market/chain/")) {
      return {
        ok: true,
        json: () =>
          Promise.resolve({
            underlying_last: "100.00",
            expiries: { "2026-04-25": { calls: [], puts: [] } },
          }),
      };
    }
    if (url.includes("/api/market/news/")) {
      return { ok: true, json: () => Promise.resolve({ items: [] }) };
    }
    if (url.includes("/api/coverage/")) {
      return {
        ok: true,
        json: () =>
          Promise.resolve({
            id: 1,
            ticker: "SPY",
            stance: "bull",
            conviction: 4,
            bull_case: "",
            bear_case: "",
            key_levels: {},
            watching_for: "",
            created_at: "2026-05-01T00:00:00Z",
            updated_at: "2026-06-01T00:00:00Z",
            revisions: [],
          }),
      };
    }
    return {
      ok: true,
      json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [] }),
    };
  });
});

describe("MarketTickerPage", () => {
  it("renders chart, chain, and news for the requested ticker", async () => {
    renderWithProviders(<MarketTickerPage />, {
      initialEntries: ["/market/SPY"],
      routePath: "/market/:ticker",
    });
    await waitFor(() => {
      expect(screen.getByText(/SPY/)).toBeInTheDocument();
    });
  });

  it("surfaces the house view and links to the coverage note", async () => {
    renderWithProviders(<MarketTickerPage />, {
      initialEntries: ["/market/SPY"],
      routePath: "/market/:ticker",
    });
    const link = await screen.findByRole("link", { name: /read the note/i });
    expect(link).toHaveAttribute("href", "/coverage/SPY");
    expect(screen.getByText(/Bullish, conviction 4\/5/)).toBeInTheDocument();
  });
});
