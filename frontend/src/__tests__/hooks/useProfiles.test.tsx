import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useCreateProfile,
  useDeleteProfile,
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
