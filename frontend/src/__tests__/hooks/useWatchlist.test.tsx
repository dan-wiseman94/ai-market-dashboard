import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAddSymbol, useRemoveSymbol, useWatchlist } from "@/hooks/useWatchlist";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";

const symbolFixture = { id: 7, ticker: "AAPL", sort_order: 0 };

const watchlistFixture = {
  id: 2,
  name: "Tech picks",
  created_at: "2026-05-17T00:00:00Z",
  symbols: [symbolFixture],
};

describe("useWatchlist", () => {
  it("fetches watchlist data when id is provided", async () => {
    mockApi({ "GET /api/watchlists/2/": watchlistFixture });
    const { result } = renderHook(() => useWatchlist(2), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe("Tech picks");
    expect(result.current.data?.symbols).toHaveLength(1);
  });

  it("is disabled when id is null", async () => {
    const { result } = renderHook(() => useWatchlist(null), { wrapper: hookWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("uses query key ['watchlist', id]", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/watchlists/2/": watchlistFixture });
    renderHook(() => useWatchlist(2), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["watchlist", 2]);
    });
  });
});

describe("useAddSymbol", () => {
  it("POSTs {ticker} to the symbols URL and invalidates ['watchlist', wid]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/watchlists/2/symbols/": symbolFixture });
    const { result } = renderHook(() => useAddSymbol(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync("AAPL");
    });
    expect(calls[0].url).toContain("/api/watchlists/2/symbols/");
    expect(calls[0].body).toMatchObject({ ticker: "AAPL" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlist", 2] });
  });
});

describe("useRemoveSymbol", () => {
  it("DELETEs the symbol URL with both wid and sid; invalidates ['watchlist', wid]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "DELETE /api/watchlists/2/symbols/7/": undefined });
    const { result } = renderHook(() => useRemoveSymbol(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(7);
    });
    expect(calls[0].url).toContain("/api/watchlists/2/symbols/7/");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlist", 2] });
  });
});
