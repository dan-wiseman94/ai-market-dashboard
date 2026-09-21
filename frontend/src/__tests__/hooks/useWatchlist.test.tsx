import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useAddSymbol,
  useRemoveSymbol,
  useReorderSymbols,
  useWatchlist,
} from "@/hooks/useWatchlist";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const symbolFixture = { id: 7, ticker: "AAPL", sort_order: 0 };

const watchlistFixture = {
  id: 2,
  name: "Tech picks",
  created_at: "2026-05-17T00:00:00Z",
  tickers: [symbolFixture],
};

describe("useWatchlist", () => {
  it("fetches watchlist data when id is provided", async () => {
    mockApi({ "GET /api/watchlists/2/": watchlistFixture });
    const { result } = renderHook(() => useWatchlist(2), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe("Tech picks");
    expect(result.current.data?.tickers).toHaveLength(1);
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
  it("POSTs {ticker} to the tickers URL and invalidates ['watchlist', wid]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/watchlists/2/tickers/": symbolFixture });
    const { result } = renderHook(() => useAddSymbol(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync("AAPL");
    });
    expect(calls[0].url).toContain("/api/watchlists/2/tickers/");
    expect(calls[0].body).toMatchObject({ ticker: "AAPL" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlist", 2] });
  });
});

describe("useRemoveSymbol", () => {
  it("DELETEs the symbol URL with both wid and sid; invalidates ['watchlist', wid]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "DELETE /api/watchlists/2/tickers/7/": undefined });
    const { result } = renderHook(() => useRemoveSymbol(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(7);
    });
    expect(calls[0].url).toContain("/api/watchlists/2/tickers/7/");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlist", 2] });
  });
});

describe("useReorderSymbols", () => {
  const twoSymbols = {
    ...watchlistFixture,
    tickers: [symbolFixture, { id: 8, ticker: "MSFT", sort_order: 1 }],
  };

  it("POSTs {order} to the reorder URL and invalidates ['watchlist', wid]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/watchlists/2/reorder/": { ok: true } });
    const { result } = renderHook(() => useReorderSymbols(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync([8, 7]);
    });
    expect(calls[0].url).toContain("/api/watchlists/2/reorder/");
    expect(calls[0].body).toMatchObject({ order: [8, 7] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlist", 2] });
  });

  it("rewrites the cached order optimistically, resequencing sort_order", async () => {
    const client = newQueryClient();
    client.setQueryData(["watchlist", 2], twoSymbols);
    mockApi({ "POST /api/watchlists/2/reorder/": { ok: true } });
    const { result } = renderHook(() => useReorderSymbols(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync([8, 7]);
    });
    const cached = client.getQueryData<typeof twoSymbols>(["watchlist", 2]);
    expect(cached?.tickers.map((s) => s.id)).toEqual([8, 7]);
    expect(cached?.tickers.map((s) => s.sort_order)).toEqual([0, 1]);
  });

  it("rolls the cache back when the reorder fails", async () => {
    const client = newQueryClient();
    client.setQueryData(["watchlist", 2], twoSymbols);
    mockApiError("POST /api/watchlists/2/reorder/", 500);
    const { result } = renderHook(() => useReorderSymbols(2), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync([8, 7]).catch(() => undefined);
    });
    const cached = client.getQueryData<typeof twoSymbols>(["watchlist", 2]);
    expect(cached?.tickers.map((s) => s.id)).toEqual([7, 8]);
  });
});
