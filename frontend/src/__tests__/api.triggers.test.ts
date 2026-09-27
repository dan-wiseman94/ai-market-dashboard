import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  deleteTrigger,
  fetchFirings,
  fetchRecentFirings,
} from "../api/triggers";

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
  ) as never;
});

describe("triggers api", () => {

  it("deleteTrigger DELETEs", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) }),
    ) as never;
    await deleteTrigger(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("DELETE");
  });

  it("fetchFirings hits /api/triggers/<id>/firings/ with page & page_size", async () => {
    await fetchFirings(42, 2, 10);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/firings/");
    expect(call[0]).toContain("page=2");
    expect(call[0]).toContain("page_size=10");
  });

  it("fetchRecentFirings hits /api/triggers/firings/recent/", async () => {
    await fetchRecentFirings(5);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/firings/recent/");
    expect(call[0]).toContain("limit=5");
  });
});
