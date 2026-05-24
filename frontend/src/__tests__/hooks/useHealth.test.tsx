import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useHealth } from "@/hooks/useHealth";
import { mockApi, mockApiError } from "../testUtils";

describe("useHealth", () => {
  it("starts in loading state", () => {
    mockApi({ "GET /api/health/": { status: "ok" } });
    const { result } = renderHook(() => useHealth());
    expect(result.current).toBe("loading");
  });

  it("transitions to 'ok' when fetch resolves with status ok", async () => {
    mockApi({ "GET /api/health/": { status: "ok" } });
    const { result } = renderHook(() => useHealth());
    await waitFor(() => expect(result.current).toBe("ok"));
  });

  it("transitions to 'down' when fetch resolves with non-ok status", async () => {
    mockApi({ "GET /api/health/": { status: "degraded" } });
    const { result } = renderHook(() => useHealth());
    await waitFor(() => expect(result.current).toBe("down"));
  });

  it("transitions to 'down' when fetch rejects", async () => {
    mockApiError("GET /api/health/", 503);
    const { result } = renderHook(() => useHealth());
    await waitFor(() => expect(result.current).toBe("down"));
  });
});
