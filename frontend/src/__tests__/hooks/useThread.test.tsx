import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useCompareMessage,
  useSendMessage,
  useStopMessage,
  useThread,
  useThreads,
} from "@/hooks/useThread";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const messageFixture = {
  id: 10,
  role: "user" as const,
  content: { text: "hello" },
  status: "done" as const,
  error: "",
  created_at: "2026-05-17T09:00:00Z",
  ai_run: null,
};

const threadFixture = {
  id: 42,
  kind: "consult" as const,
  title: "Thread A",
  profile: null,
  pinned_snapshot_id: null,
  created_at: "2026-05-17T09:00:00Z",
  messages: [messageFixture],
};

describe("useThreads", () => {
  it("returns threads on success", async () => {
    mockApi({ "GET /api/threads/": [threadFixture] });
    const { result } = renderHook(() => useThreads(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].id).toBe(42);
  });
});

describe("useThread", () => {
  it("fetches the thread when id is provided", async () => {
    mockApi({ "GET /api/threads/42/": threadFixture });
    const { result } = renderHook(() => useThread(42), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.title).toBe("Thread A");
  });

  it("is disabled (no fetch) when id is null", async () => {
    const { result } = renderHook(() => useThread(null), { wrapper: hookWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });
});

describe("useSendMessage", () => {
  it("sends body with text and optional override fields; invalidates ['thread', id]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/threads/42/send/": messageFixture });
    const { result } = renderHook(() => useSendMessage(42), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({
        text: "hello",
        override: { provider: "openai", model: "gpt-5" },
      });
    });
    expect(calls[0].body).toMatchObject({
      text: "hello",
      override_provider: "openai",
      override_model: "gpt-5",
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["thread", 42] });
  });

  it("isError on send failure", async () => {
    mockApiError("POST /api/threads/42/send/", 400);
    const { result } = renderHook(() => useSendMessage(42), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({ text: "hi" }).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCompareMessage", () => {
  it("sends branches and invalidates ['thread', id]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({
      "POST /api/threads/42/compare/": {
        user_message_id: 10,
        branches: [{ provider: "claude", model: "claude-opus-4-8", task_id: "t1" }],
      },
    });
    const { result } = renderHook(() => useCompareMessage(42), {
      wrapper: hookWrapper(client),
    });
    const branches = [{ provider: "claude", model: "claude-opus-4-8" }];
    await act(async () => {
      await result.current.mutateAsync({ text: "compare this", branches });
    });
    expect(calls[0].body).toMatchObject({ text: "compare this", branches });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["thread", 42] });
  });
});

describe("useStopMessage", () => {
  it("POSTs to stop URL with both thread and message ids; invalidates ['thread', id]", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/threads/42/stop/10/": { ok: true } });
    const { result } = renderHook(() => useStopMessage(42), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(10);
    });
    expect(calls[0].url).toContain("/api/threads/42/stop/10/");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["thread", 42] });
  });
});
