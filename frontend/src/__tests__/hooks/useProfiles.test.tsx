import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useClearProfileMemory,
  useCreateProfile,
  useDeleteProfile,
  useProfiles,
  useUpdateProfile,
} from "@/hooks/useProfiles";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";

const profileFixture = {
  id: 1,
  name: "Swing Trader",
  style: "swing",
  default_includes: [],
  default_provider: "claude",
  default_model: "claude-opus-4-8",
  active: true,
};

describe("useProfiles", () => {
  it("returns profiles on success", async () => {
    mockApi({ "GET /api/profiles/": [profileFixture] });
    const { result } = renderHook(() => useProfiles(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("Swing Trader");
  });

  it("uses query key ['profiles']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/profiles/": [] });
    renderHook(() => useProfiles(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["profiles"]);
    });
  });
});

describe("useCreateProfile", () => {
  it("mutates with body and invalidates ['profiles']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({
      "GET /api/profiles/": [],
      "POST /api/profiles/": profileFixture,
    });
    const { result } = renderHook(() => useCreateProfile(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ name: "Swing Trader", style: "swing" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["profiles"] });
  });
});

describe("useUpdateProfile", () => {
  it("sends PATCH to the profile URL and invalidates ['profiles']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "PATCH /api/profiles/1/": profileFixture });
    const { result } = renderHook(() => useUpdateProfile(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: 1, body: { name: "Updated" } });
    });
    expect(calls[0].url).toContain("/api/profiles/1/");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["profiles"] });
  });
});

describe("useDeleteProfile", () => {
  it("sends DELETE and invalidates ['profiles']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({ "DELETE /api/profiles/1/": undefined });
    const { result } = renderHook(() => useDeleteProfile(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(1);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["profiles"] });
  });
});

describe("useClearProfileMemory", () => {
  it("DELETEs the store, returns the receipt and invalidates that profile's memory", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "DELETE /api/profiles/1/memory/": { profile: 1, removed_files: 2, removed_bytes: 9 },
    });
    const { result } = renderHook(() => useClearProfileMemory(), {
      wrapper: hookWrapper(client),
    });
    let receipt;
    await act(async () => {
      receipt = await result.current.mutateAsync(1);
    });
    expect(calls[0].method).toBe("DELETE");
    expect(calls[0].url).toContain("/api/profiles/1/memory/");
    expect(receipt).toEqual({ profile: 1, removed_files: 2, removed_bytes: 9 });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["profile-memory", 1] });
  });
});
