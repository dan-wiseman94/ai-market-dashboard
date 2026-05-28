import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAiModels } from "@/hooks/useAiModels";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const modelFixture = {
  id: "claude-opus-4-8",
  name: "Claude Opus 4.8",
  provider: "claude",
  input_per_mtok: 15,
  output_per_mtok: 75,
  cached_per_mtok: 1.5,
  context_window: 1_000_000,
  supports_vision: true,
};

describe("useAiModels", () => {
  it("returns models on success and starts in loading state", async () => {
    mockApi({ "GET /api/schwab/models/": { models: [modelFixture] } });
    const { result } = renderHook(() => useAiModels(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.models).toHaveLength(1);
    expect(result.current.data?.models[0].id).toBe("claude-opus-4-8");
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/schwab/models/", 500);
    const { result } = renderHook(() => useAiModels(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key including provider filter", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/models/": { models: [] } });
    renderHook(() => useAiModels("claude"), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ai-models", "claude"]);
    });
  });

  it("uses 'all' as the default filter value in the query key", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/models/": { models: [] } });
    renderHook(() => useAiModels(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ai-models", "all"]);
    });
  });
});
