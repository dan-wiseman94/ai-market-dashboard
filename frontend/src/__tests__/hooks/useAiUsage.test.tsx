import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAiUsage } from "@/hooks/useAiUsage";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

describe("useAiUsage", () => {
  it("returns data on success and starts in loading state", async () => {
    mockApi({ "GET /api/schwab/usage/": { today: { claude: "0.0012" } } });
    const { result } = renderHook(() => useAiUsage(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.today.claude).toBe("0.0012");
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/schwab/usage/", 503);
    const { result } = renderHook(() => useAiUsage(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key ['ai-usage']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/usage/": { today: {} } });
    renderHook(() => useAiUsage(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ai-usage"]);
    });
  });
});
