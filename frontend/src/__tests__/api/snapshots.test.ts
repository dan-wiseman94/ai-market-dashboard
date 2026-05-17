import { afterEach, describe, expect, it, vi } from "vitest";
import { createSnapshot, fetchSnapshot, fetchSnapshotDiff } from "@/api/snapshots";
import { ApiError } from "@/api/client";
import { mockApiError } from "../testUtils";

// ---- Shared fixture ----

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

// Stub fetch to return a successful JSON response for a single object.
// mockApi cannot be used here because snapshotFixture has a `status` string
// field which isErrorHandler() in testUtils mistakenly treats as an error envelope.
function stubOkJson(data: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => data,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- createSnapshot ----

describe("api/snapshots", () => {
  describe("createSnapshot", () => {
    it("POSTs to /api/snapshots/ with minimal body (profile_id only)", async () => {
      const fetchMock = stubOkJson(snapshotFixture);
      const body = { profile_id: 1 };
      const res = await createSnapshot(body);
      expect(res.id).toBe(42);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(opts.method).toBe("POST");
      expect(url).toMatch(/\/api\/snapshots\/$/);
      expect(JSON.parse(opts.body as string)).toEqual(body);
    });

    it("sends full body shape pass-through when all optional fields are set", async () => {
      const fetchMock = stubOkJson(snapshotFixture);
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
      const [, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(JSON.parse(opts.body as string)).toEqual(fullBody);
    });

    it("throws ApiError with status 400 on validation error", async () => {
      mockApiError("POST /api/snapshots/", 400, "validation_error", "profile_id is required");
      const promise = createSnapshot({ profile_id: 0 } as never);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
    });
  });

  // ---- fetchSnapshot ----

  describe("fetchSnapshot", () => {
    it("GETs /api/snapshots/:id/ and returns Snapshot with sections", async () => {
      const fetchMock = stubOkJson(snapshotFixture);
      const res = await fetchSnapshot(42);
      expect(res.id).toBe(42);
      expect(res.status).toBe("ready");
      expect(res.sections).toHaveLength(1);
      expect(res.sections[0].kind).toBe("quotes");
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect((opts.method ?? "GET").toUpperCase()).toBe("GET");
      expect(url).toMatch(/\/api\/snapshots\/42\/$/);
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
      const fetchMock = stubOkJson(failedSnapshot);
      const res = await fetchSnapshot(42);
      expect(res.status).toBe("failed");
      expect(res.sections[0].status).toBe("failed");
      expect(res.sections[0].error).toBe("timeout fetching chain data");
      const [, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect((opts.method ?? "GET").toUpperCase()).toBe("GET");
    });
  });

  // ---- fetchSnapshotDiff ----

  describe("fetchSnapshotDiff", () => {
    it("GETs /api/snapshots/:id/diff/ without query param when against is not provided", async () => {
      const fetchMock = stubOkJson({ delta: "", prev_id: 0, curr_id: 42 });
      const res = await fetchSnapshotDiff(42);
      expect(res.curr_id).toBe(42);
      expect(fetchMock.mock.calls[0][0]).toBe("/api/snapshots/42/diff/");
    });

    it("includes ?against=<id> in the URL when against is provided", async () => {
      const fetchMock = stubOkJson({ delta: "section changed", prev_id: 10, curr_id: 42 });
      const res = await fetchSnapshotDiff(42, 10);
      expect(res.delta).toBe("section changed");
      expect(res.prev_id).toBe(10);
      expect(fetchMock.mock.calls[0][0]).toBe("/api/snapshots/42/diff/?against=10");
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/snapshots/42/diff/", 500, "server_error", "internal error");
      const promise = fetchSnapshotDiff(42);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });
  });
});
