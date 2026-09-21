import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useClearProfileMemory,
  useCreateProfile,
  useDeleteProfile,
  useProfileMemory,
  useProfiles,
  useUpdateProfile,
} from "@/hooks/useProfiles";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

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

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/profiles/", 500);
    const { result } = renderHook(() => useProfiles(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
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

  it("isError on mutation failure", async () => {
    mockApiError("POST /api/profiles/", 400);
    const { result } = renderHook(() => useCreateProfile(), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({}).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
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

const memoryFixture = {
  profile: 1,
  exists: true,
  entries: [
    {
      path: "notes.md",
      size_bytes: 3,
      modified_at: "2026-09-20T00:00:00Z",
      preview: "abc",
      preview_truncated: false,
    },
  ],
  total_files: 1,
  total_bytes: 3,
  preview_chars: 400,
};

describe("useProfileMemory", () => {
  it("reads the profile's memory store", async () => {
    mockApi({ "GET /api/profiles/1/memory/": memoryFixture });
    const { result } = renderHook(() => useProfileMemory(1), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.entries[0].path).toBe("notes.md");
  });

  it("stays idle (and sends nothing) for an unsaved profile", async () => {
    const { calls } = mockApi({ "GET /api/profiles/1/memory/": memoryFixture });
    const { result } = renderHook(() => useProfileMemory(null), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    expect(calls).toHaveLength(0);
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
