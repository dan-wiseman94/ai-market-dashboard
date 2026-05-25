// frontend/src/__tests__/hooks/useUpsertProviderConfig.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { hookWrapper, newQueryClient } from "../testUtils";

vi.mock("@/api/ai", () => ({
  upsertProviderConfig: vi.fn(async () => ({ provider: "claude" })),
}));

let qc: QueryClient;
beforeEach(() => { qc = newQueryClient(); });

describe("useUpsertProviderConfig", () => {
  it("invalidates provider-configs, ai-usage and costs-caps on success", async () => {
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUpsertProviderConfig(), { wrapper: hookWrapper(qc) });
    result.current.mutate({ provider: "claude", body: { enabled: true } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["provider-configs"]));
    expect(keys).toContain(JSON.stringify(["ai-usage"]));
    expect(keys).toContain(JSON.stringify(["costs-caps"]));
  });
});
