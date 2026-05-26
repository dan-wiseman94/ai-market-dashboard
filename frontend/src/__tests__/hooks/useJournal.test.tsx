import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useJournal, useCreateJournalEntry } from "@/hooks/useJournal";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const journalFixture = {
  id: 1,
  thread_id: 42,
  thesis_id: null,
  snapshot_id: null,
  decision: "acted" as const,
  note: "Went long SPY.",
  created_at: "2026-05-25T10:00:00Z",
};

const journalFixtureWithThesis = {
  id: 2,
  thread_id: 42,
  thesis_id: 7,
  snapshot_id: 3,
  decision: "passed" as const,
  note: "Too risky given macro.",
  created_at: "2026-05-24T09:00:00Z",
};

describe("useJournal", () => {
  it("fetches journal entries for a thread via GET /api/journal/?thread=N", async () => {
    mockApi({ "GET /api/journal/": [journalFixture, journalFixtureWithThesis] });
    const { result } = renderHook(() => useJournal(42), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].decision).toBe("acted");
  });

  it("is disabled when threadId is null", () => {
    const { result } = renderHook(() => useJournal(null), { wrapper: hookWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("uses query key ['journal', threadId]", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/journal/": [] });
    renderHook(() => useJournal(42), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["journal", 42]);
    });
  });

  it("calls the correct URL with thread query param", async () => {
    const { calls } = mockApi({ "GET /api/journal/": [] });
    const { result } = renderHook(() => useJournal(42), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0].url).toContain("?thread=42");
  });

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/journal/", 500);
    const { result } = renderHook(() => useJournal(42), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCreateJournalEntry", () => {
  it("POSTs correct body to /api/journal/", async () => {
    const { calls } = mockApi({
      "GET /api/journal/": [],
      "POST /api/journal/": journalFixture,
    });
    const { result } = renderHook(() => useCreateJournalEntry(), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({
        thread_id: 42,
        decision: "acted",
        note: "Went long SPY.",
        snapshot_id: 5,
      });
    });
    const postCall = calls.find((c) => c.method === "POST");
    expect(postCall?.url).toContain("/api/journal/");
    expect(postCall?.body).toMatchObject({
      thread_id: 42,
      decision: "acted",
      note: "Went long SPY.",
      snapshot_id: 5,
    });
  });

  it("POSTs with thesis_id when provided", async () => {
    const { calls } = mockApi({
      "GET /api/journal/": [],
      "POST /api/journal/": journalFixtureWithThesis,
    });
    const { result } = renderHook(() => useCreateJournalEntry(), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({
        thread_id: 42,
        decision: "passed",
        note: "Too risky.",
        thesis_id: 7,
        snapshot_id: 3,
      });
    });
    const postCall = calls.find((c) => c.method === "POST");
    expect(postCall?.body).toMatchObject({
      thesis_id: 7,
      decision: "passed",
    });
  });

  it("invalidates ['journal', thread_id] on success", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({
      "GET /api/journal/": [],
      "POST /api/journal/": journalFixture,
    });
    const { result } = renderHook(() => useCreateJournalEntry(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ thread_id: 42, decision: "acted" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["journal", 42] });
  });

  it("isError on mutation failure", async () => {
    mockApiError("POST /api/journal/", 400);
    const { result } = renderHook(() => useCreateJournalEntry(), { wrapper: hookWrapper() });
    await act(async () => {
      await result.current.mutateAsync({ thread_id: 42, decision: "watching" }).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
