import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePositions } from "@/hooks/usePositions";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const positionsFixture = [
  { ticker: "AAPL", qty: 10, avg_cost: 150.0, mkt_value: 1800.0, unrealized_pl: 300.0, day_pl: 25.0 },
  { ticker: "MSFT", qty: 5, avg_cost: 300.0, mkt_value: 1600.0, unrealized_pl: 100.0, day_pl: -10.0 },
];

describe("usePositions", () => {
  it("returns positions on success and starts in loading state", async () => {
    mockApi({ "GET /api/market/positions/": positionsFixture });
    const { result } = renderHook(() => usePositions(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].ticker).toBe("AAPL");
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/market/positions/", 500);
    const { result } = renderHook(() => usePositions(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key ['positions']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/market/positions/": positionsFixture });
    renderHook(() => usePositions(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["positions"]);
    });
  });
});
