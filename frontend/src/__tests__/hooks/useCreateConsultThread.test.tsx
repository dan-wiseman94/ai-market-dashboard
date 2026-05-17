import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useCreateConsultThread } from "@/hooks/useCreateConsultThread";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const threadFixture = {
  id: 1,
  kind: "consult",
  title: "My thread",
  profile: null,
  pinned_snapshot_id: null,
  created_at: "2026-05-17T00:00:00Z",
  messages: [],
};

describe("useCreateConsultThread", () => {
  it("returns the created Thread on success", async () => {
    mockApi({ "POST /api/threads/": threadFixture });
    const { result } = renderHook(() => useCreateConsultThread(), {
      wrapper: hookWrapper(),
    });
    let data: typeof threadFixture | undefined;
    await act(async () => {
      data = await result.current.mutateAsync({});
    });
    expect(data?.id).toBe(1);
    expect(data?.kind).toBe("consult");
  });

  it("sends kind: 'consult' merged with the body fields", async () => {
    const { calls } = mockApi({ "POST /api/threads/": threadFixture });
    const { result } = renderHook(() => useCreateConsultThread(), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ profile_id: 7, title: "test" });
    });
    expect(calls[0].body).toMatchObject({
      kind: "consult",
      profile_id: 7,
      title: "test",
    });
  });

  it("isError when the request fails", async () => {
    mockApiError("POST /api/threads/", 400);
    const { result } = renderHook(() => useCreateConsultThread(), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({}).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
