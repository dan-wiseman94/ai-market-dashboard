import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSnapshot } from "@/hooks/useSnapshot";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const snapshotFixture = {
  id: 42,
  profile_id: 1,
  objective: "Morning briefing",
  notes: "",
  status: "ready",
  includes: ["quotes", "ohlc"],
  source: "manual",
  captured_at: "2026-05-17T09:30:00Z",
  sections: [],
};

describe("useSnapshot", () => {
  it("returns snapshot data on success when id is provided", async () => {
    mockApi({ "GET /api/snapshots/42/": snapshotFixture });
    const { result } = renderHook(() => useSnapshot(42), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(42);
    expect(result.current.data?.status).toBe("ready");
    expect(result.current.data?.objective).toBe("Morning briefing");
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/snapshots/99/", 404);
    const { result } = renderHook(() => useSnapshot(99), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses query key including id", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/snapshots/42/": snapshotFixture });
    renderHook(() => useSnapshot(42), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["snapshot", 42]);
    });
  });

  it("is disabled and does not fetch when id is null", async () => {
    const mock = mockApi({ "GET /api/snapshots/": snapshotFixture });
    const { result } = renderHook(() => useSnapshot(null), { wrapper: hookWrapper() });
    // Wait a tick for any potential (erroneous) fetch
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });
});
