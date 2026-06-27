import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useAgentPresets,
  useCreatePreset,
  useDeletePreset,
  useUpdatePreset,
} from "@/hooks/useAgentPresets";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const presetFixture = {
  id: 1,
  name: "Morning Scan",
  slug: "morning-scan",
  description: "Daily morning market scan",
  objective_template: "What are the key moves this morning?",
  structured: false,
  builtin: false,
  active: true,
  created_at: "2026-05-25T00:00:00Z",
  updated_at: "2026-05-25T00:00:00Z",
};

describe("useAgentPresets", () => {
  it("returns presets on success", async () => {
    mockApi({ "GET /api/presets/": [presetFixture] });
    const { result } = renderHook(() => useAgentPresets(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("Morning Scan");
  });

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/presets/", 500);
    const { result } = renderHook(() => useAgentPresets(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses query key ['presets']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/presets/": [] });
    renderHook(() => useAgentPresets(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["presets"]);
    });
  });
});

describe("useCreatePreset", () => {
  it("posts to /api/presets/ and invalidates ['presets']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "GET /api/presets/": [],
      "POST /api/presets/": presetFixture,
    });
    const { result } = renderHook(() => useCreatePreset(), { wrapper: hookWrapper(client) });
    await act(async () => {
      await result.current.mutateAsync({
        name: "Morning Scan",
        objective_template: "What are the key moves?",
      });
    });
    expect(calls.some((c) => c.url.endsWith("/api/presets/") && c.method === "POST")).toBe(true);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["presets"] });
  });

  it("isError on mutation failure", async () => {
    mockApiError("POST /api/presets/", 400);
    const { result } = renderHook(() => useCreatePreset(), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({
        name: "Bad",
        objective_template: "",
      }).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useUpdatePreset", () => {
  it("sends PATCH to /api/presets/{id}/ and invalidates ['presets']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "PATCH /api/presets/1/": presetFixture });
    const { result } = renderHook(() => useUpdatePreset(), { wrapper: hookWrapper(client) });
    await act(async () => {
      await result.current.mutateAsync({ id: 1, body: { name: "Updated" } });
    });
    expect(calls[0].url).toContain("/api/presets/1/");
    expect(calls[0].method).toBe("PATCH");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["presets"] });
  });
});

describe("useDeletePreset", () => {
  it("sends DELETE to /api/presets/{id}/ and invalidates ['presets']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "DELETE /api/presets/1/": undefined });
    const { result } = renderHook(() => useDeletePreset(), { wrapper: hookWrapper(client) });
    await act(async () => {
      await result.current.mutateAsync(1);
    });
    expect(calls[0].url).toContain("/api/presets/1/");
    expect(calls[0].method).toBe("DELETE");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["presets"] });
  });
});
