import { describe, expect, it } from "vitest";
import {
  fetchQuotes,
  fetchOhlc,
} from "@/api/market";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// Note: setup.ts has a global afterEach that calls vi.unstubAllGlobals(),
// so each test starts with a fresh fetch.

const quoteFixture = { last: 200.5, bid: 200.0, ask: 200.5, volume: 100000, high: 201, low: 199, pct_change: 0.5 };
const ohlcBarFixture = { ts: "2026-04-18T10:00:00Z", open: 200, high: 201, low: 199, close: 200.5, volume: 100000 };

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
});
