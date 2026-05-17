import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useMarketContext } from "@/hooks/useMarketContext";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const marketContextFixture = {
  spy_last: 520.5,
  qqq_last: 440.2,
  vix_last: 14.3,
  sectors: { XLK: 1.2, XLF: -0.5 },
  breadth: { advance_decline: 0.7 },
};

describe("useMarketContext", () => {
  it("returns market context on success and starts in loading state", async () => {
    mockApi({ "GET /api/market/context/": marketContextFixture });
    const { result } = renderHook(() => useMarketContext(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.spy_last).toBe(520.5);
    expect(result.current.data?.vix_last).toBe(14.3);
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/market/context/", 500);
    const { result } = renderHook(() => useMarketContext(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key ['market-context']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/market/context/": marketContextFixture });
    renderHook(() => useMarketContext(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["market-context"]);
    });
  });
});
