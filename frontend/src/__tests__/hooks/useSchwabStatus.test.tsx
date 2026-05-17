import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const schwabStatusFixture = {
  connected: true,
  expires_at: "2026-05-17T16:00:00Z",
};

describe("useSchwabStatus", () => {
  it("returns status on success with connected and expires_at", async () => {
    mockApi({ "GET /api/schwab/status/": schwabStatusFixture });
    const { result } = renderHook(() => useSchwabStatus(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.connected).toBe(true);
    expect(result.current.data?.expires_at).toBe("2026-05-17T16:00:00Z");
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/schwab/status/", 500);
    const { result } = renderHook(() => useSchwabStatus(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key ['schwab', 'status']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/status/": schwabStatusFixture });
    renderHook(() => useSchwabStatus(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["schwab", "status"]);
    });
  });
});
