import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useOhlc } from "@/hooks/useOhlc";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";

const ohlcFixture = {
  ticker: "AAPL",
  timeframe: "5m",
  bars: [
    { ts: "2026-05-17T09:30:00Z", open: 180.0, high: 181.5, low: 179.5, close: 181.0, volume: 12345 },
  ],
};

describe("useOhlc", () => {

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
