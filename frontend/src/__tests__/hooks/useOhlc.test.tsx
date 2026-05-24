import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useOhlc } from "@/hooks/useOhlc";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const ohlcFixture = {
  ticker: "AAPL",
  timeframe: "5m",
  bars: [
    { ts: "2026-05-17T09:30:00Z", open: 180.0, high: 181.5, low: 179.5, close: 181.0, volume: 12345 },
  ],
};

describe("useOhlc", () => {
  it("returns OHLC data on success and starts in loading state", async () => {
    mockApi({ "GET /api/market/ohlc/": ohlcFixture });
    const { result } = renderHook(() => useOhlc("AAPL", "5m", 60), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.ticker).toBe("AAPL");
    expect(result.current.data?.bars).toHaveLength(1);
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/market/ohlc/", 503);
    const { result } = renderHook(() => useOhlc("AAPL", "5m"), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key including ticker, timeframe, and bars", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/market/ohlc/": ohlcFixture });
    renderHook(() => useOhlc("AAPL", "5m", 60), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ohlc", "AAPL", "5m", 60]);
    });
  });

  it("is disabled and does not fetch when ticker is empty string", async () => {
    const mock = mockApi({ "GET /api/market/ohlc/": ohlcFixture });
    const { result } = renderHook(() => useOhlc("", "5m"), { wrapper: hookWrapper() });
    // Wait a tick for any potential (erroneous) fetch
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });
});
