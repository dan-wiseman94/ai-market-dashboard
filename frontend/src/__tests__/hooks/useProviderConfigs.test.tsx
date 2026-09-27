import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useProviderConfigs, useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";

const configFixture = {
  provider: "claude" as const,
  base_url: "",
  default_model: "claude-opus-4-8",
  enabled: true,
  supports_vision: true,
  daily_cost_cap_usd: "10.00",
  monthly_cost_cap_usd: null,
  api_key_present: true,
};

describe("useProviderConfigs", () => {
  it("returns provider configs on success", async () => {
    mockApi({ "GET /api/schwab/providers/": [configFixture] });
    const { result } = renderHook(() => useProviderConfigs(), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].provider).toBe("claude");
  });
});

describe("useUpsertProviderConfig", () => {

  it("falls back to POST when PATCH returns 404", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "PATCH /api/schwab/providers/local/": { status: 404, code: "not_found", message: "not found" },
      "POST /api/schwab/providers/": { ...configFixture, provider: "local" },
    });
    const { result } = renderHook(() => useUpsertProviderConfig(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ provider: "local", body: { enabled: true } });
    });
    const methods = calls.map((c) => c.method);
    expect(methods).toContain("PATCH");
    expect(methods).toContain("POST");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["provider-configs"] });
  });
});
