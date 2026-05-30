import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useErrors, useResolveError } from "@/hooks/useErrors";
import { mockApi, hookWrapper, newQueryClient } from "./testUtils";
import type { FetchMock } from "./testUtils";

const ALL_ERRORS_RESPONSE = {
  errors: [
    {
      id: 1,
      level: "error",
      source: "capture_task",
      message: "Connection timeout fetching quotes",
      fingerprint: "abc123",
      resolved: false,
      created_at: "2026-05-30T10:00:00Z",
    },
    {
      id: 2,
      level: "warning",
      source: "observer",
      message: "Retried after backoff",
      fingerprint: "def456",
      resolved: true,
      created_at: "2026-05-30T09:00:00Z",
    },
  ],
  count: 2,
};

const UNRESOLVED_RESPONSE = {
  errors: [ALL_ERRORS_RESPONSE.errors[0]],
  count: 1,
};

describe("useErrors", () => {
  let fm: FetchMock;

  beforeEach(() => {
    // mockApi strips query strings for path matching; use a function handler
    // that checks the full URL to return different data per flag.
    fm = mockApi({
      "GET /api/errors/": (_body: unknown, url: string) => {
        return url.includes("unresolved=true")
          ? UNRESOLVED_RESPONSE
          : ALL_ERRORS_RESPONSE;
      },
    });
  });

  afterEach(() => {
    fm.restore();
    vi.restoreAllMocks();
  });

  it("fetches /api/errors/?unresolved=false by default and returns rows", async () => {
    const { result } = renderHook(() => useErrors(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.errors).toHaveLength(2);
    expect(result.current.data?.errors[0].source).toBe("capture_task");
    expect(result.current.data?.errors[0].message).toBe(
      "Connection timeout fetching quotes",
    );
    expect(result.current.data?.errors[0].level).toBe("error");
    expect(result.current.data?.count).toBe(2);

    const getCall = fm.calls.find(
      (c) => c.method === "GET" && c.url.includes("/api/errors/"),
    );
    expect(getCall?.url).toContain("unresolved=false");
  });

  it("fetches /api/errors/?unresolved=true when flag is set", async () => {
    const { result } = renderHook(() => useErrors(true), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.errors).toHaveLength(1);
    expect(result.current.data?.errors[0].source).toBe("capture_task");

    const getCall = fm.calls.find(
      (c) => c.method === "GET" && c.url.includes("/api/errors/"),
    );
    expect(getCall?.url).toContain("unresolved=true");
  });
});

describe("useResolveError", () => {
  let fm: FetchMock;

  beforeEach(() => {
    fm = mockApi({
      "GET /api/errors/": ALL_ERRORS_RESPONSE,
      "POST /api/errors/1/resolve/": undefined,
    });
  });

  afterEach(() => {
    fm.restore();
    vi.restoreAllMocks();
  });

  it("POSTs to /api/errors/<id>/resolve/ and invalidates the errors query", async () => {
    const qc = newQueryClient();
    const { result } = renderHook(() => useResolveError(), {
      wrapper: hookWrapper(qc),
    });

    result.current.mutate(1);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const postCall = fm.calls.find(
      (c) => c.method === "POST" && c.url.includes("/api/errors/1/resolve/"),
    );
    expect(postCall).toBeDefined();
    expect(postCall?.url).toContain("/api/errors/1/resolve/");
  });
});
