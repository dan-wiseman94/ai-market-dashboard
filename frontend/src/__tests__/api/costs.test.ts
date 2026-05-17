import { describe, expect, it } from "vitest";
import {
  fetchCostsToday,
  fetchCostsSummary,
  fetchCostsCaps,
  fetchCostsSnapshot,
} from "@/api/costs";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// Shared fixture so individual tests don't repeat the full literal.
const costsSummary = {
  total: "1.2345",
  by_provider: [
    {
      provider: "claude",
      cost_usd: "1.0000",
      runs: 5,
      input_tokens: 10000,
      output_tokens: 2000,
      cached_tokens: 500,
    },
  ],
  by_model: [
    {
      provider: "claude",
      model: "claude-opus-4-7",
      cost_usd: "1.0000",
      runs: 5,
      input_tokens: 10000,
      output_tokens: 2000,
      cached_tokens: 500,
    },
  ],
  by_thread: [{ thread_id: 1, title: "My thread", cost_usd: "0.2345", runs: 2 }],
  daily: [{ date: "2026-05-17", cost_usd: "1.2345", runs: 5 }],
};

describe("api/costs", () => {
  describe("fetchCostsToday", () => {
    it("GETs /api/costs/today/ and returns shaped data", async () => {
      const payload = {
        total_usd: "0.0042",
        by_provider: [
          {
            provider: "claude",
            cost_usd: "0.0042",
            runs: 1,
            input_tokens: 500,
            output_tokens: 100,
            cached_tokens: 0,
          },
        ],
      };
      const api = mockApi({ "GET /api/costs/today/": payload });
      const res = await fetchCostsToday();
      expect(res.total_usd).toBe("0.0042");
      expect(res.by_provider).toHaveLength(1);
      expect(res.by_provider[0].provider).toBe("claude");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/costs\/today\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/costs/today/", 500, "server_error", "internal error");
      const promise = fetchCostsToday();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("throws ApiError with status 503 on service unavailable", async () => {
      mockApiError("GET /api/costs/today/", 503, "unavailable", "down");
      await expect(fetchCostsToday()).rejects.toMatchObject({ status: 503 });
    });
  });

  describe("fetchCostsSummary", () => {
    it("GETs /api/costs/summary with correct from/to query params", async () => {
      const api = mockApi({ "GET /api/costs/summary": costsSummary });
      const res = await fetchCostsSummary({ from: "2026-05-01", to: "2026-05-17" });
      expect(res.total).toBe("1.2345");
      expect(res.by_provider).toHaveLength(1);
      expect(res.daily).toHaveLength(1);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toContain("from=2026-05-01");
      expect(api.calls[0].url).toContain("to=2026-05-17");
    });

    it("percent-encodes ISO datetime strings with colons and T", async () => {
      const api = mockApi({ "GET /api/costs/summary": costsSummary });
      await fetchCostsSummary({
        from: "2026-05-01T00:00:00Z",
        to: "2026-05-17T23:59:59Z",
      });
      const url = api.calls[0].url;
      // T and : must be encoded; raw colons in query params would be wrong
      expect(url).toContain("from=2026-05-01T00%3A00%3A00Z");
      expect(url).toContain("to=2026-05-17T23%3A59%3A59Z");
    });

    it("throws ApiError with status 400 on bad range", async () => {
      mockApiError("GET /api/costs/summary", 400, "bad_request", "invalid range");
      const promise = fetchCostsSummary({ from: "bad", to: "worse" });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "bad_request" });
    });
  });

  describe("fetchCostsCaps", () => {
    it("GETs /api/costs/caps and returns cap rows", async () => {
      const caps = [
        {
          provider: "claude",
          daily: { cap: "5.00", spent: "1.23", pct: 24.6 },
          monthly: { cap: "100.00", spent: "30.00", pct: 30.0 },
        },
      ];
      const api = mockApi({ "GET /api/costs/caps": caps });
      const res = await fetchCostsCaps();
      expect(res).toHaveLength(1);
      expect(res[0].provider).toBe("claude");
      expect(res[0].daily.pct).toBe(24.6);
      expect(res[0].monthly).not.toBeNull();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/costs\/caps$/);
    });

    it("returns an empty array when no caps are configured", async () => {
      mockApi({ "GET /api/costs/caps": [] });
      const res = await fetchCostsCaps();
      expect(res).toEqual([]);
    });

    it("throws ApiError with status 401 when unauthenticated", async () => {
      mockApiError("GET /api/costs/caps", 401, "unauthorized", "login required");
      const promise = fetchCostsCaps();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    });
  });

  describe("fetchCostsSnapshot", () => {
    it("GETs /api/costs/snapshot/:id with the correct snapshot ID in the URL", async () => {
      const breakdown = [
        { section: "quotes", payload_tokens: 800, cost_share_usd: "0.0012" },
        { section: "chain", payload_tokens: 4200, cost_share_usd: "0.0063" },
      ];
      const api = mockApi({ "GET /api/costs/snapshot/99": breakdown });
      const res = await fetchCostsSnapshot(99);
      expect(res).toHaveLength(2);
      expect(res[0].section).toBe("quotes");
      expect(res[1].payload_tokens).toBe(4200);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/costs\/snapshot\/99$/);
    });

    it("embeds the snapshot ID correctly for different IDs", async () => {
      const api = mockApi({ "GET /api/costs/snapshot/1": [] });
      await fetchCostsSnapshot(1);
      expect(api.calls[0].url).toMatch(/\/api\/costs\/snapshot\/1$/);
    });

    it("throws ApiError with status 404 when snapshot does not exist", async () => {
      mockApiError("GET /api/costs/snapshot/999", 404, "not_found", "snapshot missing");
      const promise = fetchCostsSnapshot(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });
  });
});
