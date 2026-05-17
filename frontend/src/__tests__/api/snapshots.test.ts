import { describe, expect, it } from "vitest";
import { createSnapshot, fetchSnapshot, fetchSnapshotDiff } from "@/api/snapshots";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

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

    it("sends full body shape pass-through when all optional fields are set", async () => {
      const api = mockApi({ "POST /api/snapshots/": snapshotFixture });
      const fullBody = {
        profile_id: 1,
        objective: "Full scan",
        notes: "EOD review",
        includes: ["quotes", "ohlc", "chain", "news"],
        watchlist_tickers: ["AAPL", "MSFT"],
        ohlc_ticker: "SPY",
        ohlc_timeframe: "5m",
        ohlc_bars: 100,
        image_ids: [7, 8],
      };
      const res = await createSnapshot(fullBody);
      expect(res.id).toBe(42);
      expect(api.calls[0].body).toEqual(fullBody);
    });

    it("throws ApiError with status 400 on validation error", async () => {
      mockApiError("POST /api/snapshots/", 400, "validation_error", "profile_id is required");
      const promise = createSnapshot({ profile_id: 0 } as never);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
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

    it("throws ApiError with status 404 when snapshot does not exist", async () => {
      mockApiError("GET /api/snapshots/999/", 404, "not_found", "snapshot missing");
      const promise = fetchSnapshot(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("handles a failed snapshot with section-level error strings", async () => {
      const failedSnapshot = {
        ...snapshotFixture,
        status: "failed" as const,
        sections: [
          {
            id: 102,
            kind: "chain",
            status: "failed" as const,
            payload: null,
            error: "timeout fetching chain data",
          },
        ],
      };
      const api = mockApi({ "GET /api/snapshots/42/": failedSnapshot });
      const res = await fetchSnapshot(42);
      expect(res.status).toBe("failed");
      expect(res.sections[0].status).toBe("failed");
      expect(res.sections[0].error).toBe("timeout fetching chain data");
      expect(api.calls[0].method).toBe("GET");
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

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/snapshots/42/diff/", 500, "server_error", "internal error");
      const promise = fetchSnapshotDiff(42);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });
  });
});
