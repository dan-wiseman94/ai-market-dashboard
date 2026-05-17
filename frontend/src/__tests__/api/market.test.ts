import { describe, expect, it } from "vitest";
import {
  fetchQuotes,
  fetchOhlc,
  fetchPositions,
  fetchMarketContext,
} from "@/api/market";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// Note: setup.ts has a global afterEach that calls vi.unstubAllGlobals(),
// so each test starts with a fresh fetch.

const quoteFixture = { last: 200.5, bid: 200.0, ask: 200.5, volume: 100000, high: 201, low: 199, pct_change: 0.5 };
const ohlcBarFixture = { ts: "2026-04-18T10:00:00Z", open: 200, high: 201, low: 199, close: 200.5, volume: 100000 };
const positionFixture = { ticker: "AAPL", qty: 10, avg_cost: 180, mkt_value: 2005, unrealized_pl: 205, day_pl: 5 };
const contextFixture = {
  spy_last: 500, qqq_last: 450, vix_last: 15,
  sectors: { tech: 0.5, finance: -0.2 },
  breadth: { advancers: 1500, decliners: 800 },
};

describe("api/market", () => {
  describe("fetchQuotes", () => {
    it("GETs quotes map with tickers encoded as comma-joined query param", async () => {
      const api = mockApi({ "GET /api/market/quotes/": { AAPL: quoteFixture, MSFT: quoteFixture } });
      const res = await fetchQuotes(["AAPL", "MSFT"]);
      expect(res).toEqual({ AAPL: quoteFixture, MSFT: quoteFixture });
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/market\/quotes\//);
      expect(api.calls[0].url).toContain("tickers=AAPL%2CMSFT");
    });

    it("throws ApiError with status 502 on bad gateway", async () => {
      mockApiError("GET /api/market/quotes/", 502, "bad_gateway", "upstream failure");
      const promise = fetchQuotes(["AAPL"]);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 502 });
    });

    it("sends empty tickers param when given an empty array", async () => {
      const api = mockApi({ "GET /api/market/quotes/": {} });
      await fetchQuotes([]);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toContain("tickers=");
    });
  });

  describe("fetchOhlc", () => {
    it("GETs OHLC bars with ticker, timeframe and default bars=60 in URL", async () => {
      const payload = { ticker: "AAPL", timeframe: "1m", bars: [ohlcBarFixture] };
      const api = mockApi({ "GET /api/market/ohlc/": payload });
      const res = await fetchOhlc("AAPL", "1m");
      expect(res.ticker).toBe("AAPL");
      expect(res.timeframe).toBe("1m");
      expect(res.bars).toHaveLength(1);
      expect(res.bars[0]).toEqual(ohlcBarFixture);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toContain("ticker=AAPL");
      expect(api.calls[0].url).toContain("timeframe=1m");
      expect(api.calls[0].url).toContain("bars=60");
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/market/ohlc/", 500, "server_error", "internal error");
      const promise = fetchOhlc("AAPL", "1m");
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500 });
    });

    it("uses custom bars value in URL when provided", async () => {
      const payload = { ticker: "TSLA", timeframe: "5m", bars: [] };
      const api = mockApi({ "GET /api/market/ohlc/": payload });
      await fetchOhlc("TSLA", "5m", 120);
      expect(api.calls[0].url).toContain("bars=120");
      expect(api.calls[0].url).toContain("ticker=TSLA");
      expect(api.calls[0].url).toContain("timeframe=5m");
    });
  });

  describe("fetchPositions", () => {
    it("GETs array of positions from /api/market/positions/", async () => {
      const api = mockApi({ "GET /api/market/positions/": [positionFixture] });
      const res = await fetchPositions();
      expect(res).toHaveLength(1);
      expect(res[0]).toEqual(positionFixture);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/market\/positions\/$/);
    });

    it("throws ApiError with status 401 when unauthenticated", async () => {
      mockApiError("GET /api/market/positions/", 401, "unauthorized", "login required");
      const promise = fetchPositions();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 401 });
    });

    it("returns empty array when there are no positions", async () => {
      mockApi({ "GET /api/market/positions/": [] });
      const res = await fetchPositions();
      expect(res).toEqual([]);
    });
  });

  describe("fetchMarketContext", () => {
    it("GETs market context with spy/qqq/vix and sectors/breadth maps", async () => {
      const api = mockApi({ "GET /api/market/context/": contextFixture });
      const res = await fetchMarketContext();
      expect(res.spy_last).toBe(500);
      expect(res.qqq_last).toBe(450);
      expect(res.vix_last).toBe(15);
      expect(res.sectors).toEqual({ tech: 0.5, finance: -0.2 });
      expect(res.breadth).toEqual({ advancers: 1500, decliners: 800 });
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/market\/context\/$/);
    });

    it("throws ApiError with status 503 on service unavailable", async () => {
      mockApiError("GET /api/market/context/", 503, "unavailable", "service down");
      const promise = fetchMarketContext();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503 });
    });

    it("preserves null values in numeric fields", async () => {
      const nullContext = { spy_last: null, qqq_last: null, vix_last: null, sectors: {}, breadth: {} };
      mockApi({ "GET /api/market/context/": nullContext });
      const res = await fetchMarketContext();
      expect(res.spy_last).toBeNull();
      expect(res.qqq_last).toBeNull();
      expect(res.vix_last).toBeNull();
    });
  });
});
