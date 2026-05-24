import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useQuotes } from "@/hooks/useQuotes";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const quotesFixture = {
  AAPL: { last: 181.5, bid: 181.4, ask: 181.6, volume: 50000, high: 182.0, low: 180.0, pct_change: 0.5 },
  MSFT: { last: 320.0, bid: 319.9, ask: 320.1, volume: 30000, high: 321.0, low: 318.5, pct_change: -0.2 },
};

describe("useQuotes", () => {
  it("returns quotes map on success with non-empty tickers", async () => {
    mockApi({ "GET /api/market/quotes/": quotesFixture });
    const { result } = renderHook(() => useQuotes(["AAPL", "MSFT"]), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.AAPL.last).toBe(181.5);
    expect(result.current.data?.MSFT.last).toBe(320.0);
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/market/quotes/", 503);
    const { result } = renderHook(() => useQuotes(["AAPL"]), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("sorts ticker input for stable query key", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/market/quotes/": quotesFixture });
    // Input order is reversed — key should still use sorted order
    renderHook(() => useQuotes(["MSFT", "AAPL"]), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["quotes", "AAPL,MSFT"]);
    });
  });

  it("is disabled and does not fetch when tickers is empty", async () => {
    const mock = mockApi({ "GET /api/market/quotes/": quotesFixture });
    const { result } = renderHook(() => useQuotes([]), { wrapper: hookWrapper() });
    // Wait a tick for any potential (erroneous) fetch
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("uses stable query key ['quotes', sorted-ticker-string]", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/market/quotes/": { AAPL: quotesFixture.AAPL } });
    renderHook(() => useQuotes(["AAPL"]), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["quotes", "AAPL"]);
    });
  });
});
