import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useTheses, useThesis, useCreateThesis, useCloseThesis, useDeleteThesis } from "@/hooks/useTheses";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const thesisFixture = {
  id: 1,
  title: "SPY hits 600",
  ticker: "SPY",
  direction: "bullish" as const,
  rationale: "Strong momentum",
  conviction: 4,
  entry_price: "550.00",
  target_price: "600.00",
  invalidation_price: "520.00",
  horizon_days: 90,
  status: "open" as const,
  profile: null,
  thread: 42,
  snapshot: null,
  review_thread: null,
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_note: "",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

describe("useTheses", () => {
  it("returns theses on success", async () => {
    mockApi({ "GET /api/theses/": [thesisFixture] });
    const { result } = renderHook(() => useTheses(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].ticker).toBe("SPY");
  });

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/theses/", 500);
    const { result } = renderHook(() => useTheses(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses query key ['theses']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/theses/": [] });
    renderHook(() => useTheses(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["theses"]);
    });
  });
});

describe("useThesis", () => {
  it("fetches a single thesis when id is provided", async () => {
    mockApi({ "GET /api/theses/1/": thesisFixture });
    const { result } = renderHook(() => useThesis(1), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.title).toBe("SPY hits 600");
  });

  it("is disabled when id is null", () => {
    const { result } = renderHook(() => useThesis(null), { wrapper: hookWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });
});

describe("useCreateThesis", () => {
  it("POSTs body and invalidates ['theses']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "GET /api/theses/": [],
      "POST /api/theses/": thesisFixture,
    });
    const { result } = renderHook(() => useCreateThesis(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({
        title: "SPY hits 600",
        ticker: "SPY",
        direction: "bullish",
        conviction: 4,
        thread_id: 42,
        snapshot_id: null,
      });
    });
    expect(calls[0].body).toMatchObject({
      title: "SPY hits 600",
      ticker: "SPY",
      direction: "bullish",
      conviction: 4,
      thread_id: 42,
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["theses"] });
  });

  it("isError on mutation failure", async () => {
    mockApiError("POST /api/theses/", 400);
    const { result } = renderHook(() => useCreateThesis(), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({ title: "t", ticker: "T", direction: "bullish" }).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCloseThesis", () => {
  it("POSTs to close URL and invalidates both ['theses'] and ['theses', id]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "POST /api/theses/1/close/": { ...thesisFixture, status: "closed_win" },
    });
    const { result } = renderHook(() => useCloseThesis(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: 1, body: { status: "closed_win", close_note: "Nailed it" } });
    });
    expect(calls[0].url).toContain("/api/theses/1/close/");
    expect(calls[0].body).toMatchObject({ status: "closed_win", close_note: "Nailed it" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["theses"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["theses", 1] });
  });
});

describe("useDeleteThesis", () => {
  it("sends DELETE and invalidates ['theses']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({ "DELETE /api/theses/1/": undefined });
    const { result } = renderHook(() => useDeleteThesis(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(1);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["theses"] });
  });
});
