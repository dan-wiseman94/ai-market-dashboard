import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useCreateWatchlist,
  useDeleteWatchlist,
  useRenameWatchlist,
  useWatchlists,
} from "@/hooks/useWatchlists";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const watchlistFixture = {
  id: 1,
  name: "My list",
  created_at: "2026-05-17T00:00:00Z",
  symbols: [],
};

describe("useWatchlists", () => {
  it("returns watchlists on success", async () => {
    mockApi({ "GET /api/watchlists/": [watchlistFixture] });
    const { result } = renderHook(() => useWatchlists(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("My list");
  });

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/watchlists/", 500);
    const { result } = renderHook(() => useWatchlists(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCreateWatchlist", () => {
  it("POSTs {name} and invalidates ['watchlists']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/watchlists/": watchlistFixture });
    const { result } = renderHook(() => useCreateWatchlist(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync("My list");
    });
    expect(calls[0].body).toMatchObject({ name: "My list" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlists"] });
  });
});

describe("useRenameWatchlist", () => {
  it("PATCHes {name} to the watchlist URL and invalidates ['watchlists']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "PATCH /api/watchlists/1/": watchlistFixture });
    const { result } = renderHook(() => useRenameWatchlist(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: 1, name: "Renamed" });
    });
    expect(calls[0].url).toContain("/api/watchlists/1/");
    expect(calls[0].body).toMatchObject({ name: "Renamed" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlists"] });
  });
});

describe("useDeleteWatchlist", () => {
  it("sends DELETE and invalidates ['watchlists']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({ "DELETE /api/watchlists/1/": undefined });
    const { result } = renderHook(() => useDeleteWatchlist(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(1);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["watchlists"] });
  });
});
