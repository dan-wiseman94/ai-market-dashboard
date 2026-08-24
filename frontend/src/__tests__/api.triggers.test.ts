import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchTriggers, createTrigger, updateTrigger, deleteTrigger,
  fireTriggerNow, evaluateTrigger, fetchFirings, fetchRecentFirings,
  type Condition,
} from "../api/triggers";

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }),
  ) as never;
});

describe("triggers api", () => {
  it("fetchTriggers hits /api/triggers/", async () => {
    await fetchTriggers();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/triggers/"),
      expect.any(Object),
    );
  });

  it("createTrigger POSTs the body", async () => {
    const cond: Condition = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    await createTrigger({ name: "r", profile: 1, condition: cond, cooldown_seconds: 1800, enabled: true });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body).name).toBe("r");
  });

  it("updateTrigger PATCHes /api/triggers/<id>/", async () => {
    await updateTrigger(42, { enabled: false });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/");
    expect(call[1].method).toBe("PATCH");
  });

  it("deleteTrigger DELETEs", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) }),
    ) as never;
    await deleteTrigger(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("DELETE");
  });

  it("fireTriggerNow hits /fire/", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true, status: 202, json: () => Promise.resolve({ task_id: "t" }),
    })) as never;
    await fireTriggerNow(42);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/42/fire/");
  });

  it("evaluateTrigger POSTs to /evaluate/", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true, status: 200, json: () => Promise.resolve({ matched: true, values: {}, missing: [] }),
    })) as never;
    await evaluateTrigger({ condition: { metric: "vix", op: ">", value: 20 } });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/triggers/evaluate/");
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
