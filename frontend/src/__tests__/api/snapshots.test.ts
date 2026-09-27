import { describe, expect, it, vi } from "vitest";
import {
  createSnapshot,
  fetchSnapshot,
  fetchSnapshotDiff,
  waitForSnapshotReady,
} from "@/api/snapshots";
import { ApiError } from "@/api/client";
import { mockApi } from "../testUtils";

const snapshotFixture = {
  id: 42,
  profile_id: 1,
  objective: "Check morning market conditions",
  notes: "Pre-market scan",
  status: "ready" as const,
  includes: ["quotes", "ohlc", "news"],
  source: "manual",
  captured_at: "2026-05-17T09:30:00Z",
  sections: [
    {
      id: 101,
      kind: "quotes",
      status: "done" as const,
      payload: { AAPL: { price: 195.5 } },
      error: "",
    },
  ],
};

describe("api/snapshots", () => {
  describe("createSnapshot", () => {
    it("POSTs to /api/snapshots/ with minimal body (profile_id only)", async () => {
      const api = mockApi({ "POST /api/snapshots/": snapshotFixture });
      const body = { profile_id: 1 };
      const res = await createSnapshot(body);
      expect(res.id).toBe(42);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/snapshots\/$/);
      expect(api.calls[0].body).toEqual(body);
    });
  });

  describe("fetchSnapshot", () => {
    it("GETs /api/snapshots/:id/ and returns Snapshot with sections", async () => {
      const api = mockApi({ "GET /api/snapshots/42/": snapshotFixture });
      const res = await fetchSnapshot(42);
      expect(res.id).toBe(42);
      expect(res.status).toBe("ready");
      expect(res.sections).toHaveLength(1);
      expect(res.sections[0].kind).toBe("quotes");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/snapshots\/42\/$/);
    });
  });

  describe("fetchSnapshotDiff", () => {
    it("GETs /api/snapshots/:id/diff/ without query param when against is not provided", async () => {
      const api = mockApi({ "GET /api/snapshots/42/diff/": { delta: "", prev_id: 0, curr_id: 42 } });
      const res = await fetchSnapshotDiff(42);
      expect(res.curr_id).toBe(42);
      expect(api.calls[0].url).toBe("/api/snapshots/42/diff/");
    });

    it("includes ?against=<id> in the URL when against is provided", async () => {
      const api = mockApi({ "GET /api/snapshots/42/diff/": { delta: "section changed", prev_id: 10, curr_id: 42 } });
      const res = await fetchSnapshotDiff(42, 10);
      expect(res.delta).toBe("section changed");
      expect(res.prev_id).toBe(10);
      expect(api.calls[0].url).toBe("/api/snapshots/42/diff/?against=10");
    });
  });

  describe("waitForSnapshotReady", () => {
    // Capture runs asynchronously in a Celery worker, so createSnapshot returns
    // status="pending". This helper polls until the snapshot reaches a terminal
    // status before callers pin it to a thread (which 400s on a non-ready snap).
    it("polls until status flips to ready and resolves with the ready snapshot", async () => {
      const fetch = vi
        .fn()
        .mockResolvedValueOnce({ ...snapshotFixture, status: "pending" })
        .mockResolvedValueOnce({ ...snapshotFixture, status: "pending" })
        .mockResolvedValueOnce({ ...snapshotFixture, status: "ready" });
      const res = await waitForSnapshotReady(42, { intervalMs: 0, fetch });
      expect(res.status).toBe("ready");
      expect(fetch).toHaveBeenCalledTimes(3);
      expect(fetch).toHaveBeenCalledWith(42);
    });

    it("resolves with a single fetch when already ready", async () => {
      const fetch = vi.fn().mockResolvedValue({ ...snapshotFixture, status: "ready" });
      const res = await waitForSnapshotReady(42, { intervalMs: 0, fetch });
      expect(res.status).toBe("ready");
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("throws ApiError when capture fails", async () => {
      const fetch = vi.fn().mockResolvedValue({ ...snapshotFixture, status: "failed" });
      const promise = waitForSnapshotReady(42, { intervalMs: 0, fetch });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: "snapshot_failed" });
    });

    it("throws ApiError when capture does not finish before the timeout", async () => {
      const fetch = vi.fn().mockResolvedValue({ ...snapshotFixture, status: "pending" });
      const promise = waitForSnapshotReady(42, { intervalMs: 0, timeoutMs: 0, fetch });
      await expect(promise).rejects.toMatchObject({ code: "snapshot_timeout" });
    });
  });
});
