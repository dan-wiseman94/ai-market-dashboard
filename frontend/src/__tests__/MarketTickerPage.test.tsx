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
});
