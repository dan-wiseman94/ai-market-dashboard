import { describe, expect, it } from "vitest";
import {
  fetchWatchlists,
  fetchWatchlist,
  createWatchlist,
  renameWatchlist,
  deleteWatchlist,
  addSymbol,
  removeSymbol,
  reorderSymbols,
} from "@/api/watchlists";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

const symbolFixture = { id: 10, ticker: "AAPL", sort_order: 0 };

const watchlistFixture = {
  id: 1,
  name: "Tech Picks",
  created_at: "2026-05-17T09:00:00Z",
  tickers: [symbolFixture],
};

describe("api/watchlists", () => {
  describe("fetchWatchlists", () => {
    it("GETs /api/watchlists/ and returns Watchlist[]", async () => {
      const api = mockApi({ "GET /api/watchlists/": [watchlistFixture] });
      const res = await fetchWatchlists();
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe(1);
      expect(res[0].name).toBe("Tech Picks");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/$/);
    });
  });

  describe("fetchWatchlist", () => {
    it("GETs /api/watchlists/:id/ and returns Watchlist with tickers", async () => {
      const api = mockApi({ "GET /api/watchlists/1/": watchlistFixture });
      const res = await fetchWatchlist(1);
      expect(res.id).toBe(1);
      expect(res.tickers).toHaveLength(1);
      expect(res.tickers[0].ticker).toBe("AAPL");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/$/);
    });
  });

  describe("createWatchlist", () => {
    it("POSTs /api/watchlists/ with {name} body and returns Watchlist", async () => {
      const api = mockApi({ "POST /api/watchlists/": watchlistFixture });
      const res = await createWatchlist("Tech Picks");
      expect(res.id).toBe(1);
      expect(res.name).toBe("Tech Picks");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/$/);
      expect(api.calls[0].body).toEqual({ name: "Tech Picks" });
    });
  });

  describe("renameWatchlist", () => {
    it("PATCHes /api/watchlists/:id/ with {name} body and returns Watchlist", async () => {
      const renamed = { ...watchlistFixture, name: "Renamed List" };
      const api = mockApi({ "PATCH /api/watchlists/1/": renamed });
      const res = await renameWatchlist(1, "Renamed List");
      expect(res.name).toBe("Renamed List");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("PATCH");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/$/);
      expect(api.calls[0].body).toEqual({ name: "Renamed List" });
    });
  });

  describe("deleteWatchlist", () => {
    it("DELETEs /api/watchlists/:id/ and resolves on 204", async () => {
      const api = mockApi({ "DELETE /api/watchlists/1/": undefined });
      await expect(deleteWatchlist(1)).resolves.not.toThrow();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("DELETE");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/$/);
    });
  });

  describe("addSymbol", () => {
    it("POSTs /api/watchlists/:wid/tickers/ with {ticker} body and returns WatchlistSymbol", async () => {
      const api = mockApi({ "POST /api/watchlists/1/tickers/": symbolFixture });
      const res = await addSymbol(1, "AAPL");
      expect(res.id).toBe(10);
      expect(res.ticker).toBe("AAPL");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/tickers\/$/);
      expect(api.calls[0].body).toEqual({ ticker: "AAPL" });
    });
  });

  describe("removeSymbol", () => {
    it("DELETEs /api/watchlists/:wid/tickers/:sid/ and resolves on 204", async () => {
      const api = mockApi({ "DELETE /api/watchlists/1/tickers/10/": undefined });
      await expect(removeSymbol(1, 10)).resolves.not.toThrow();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("DELETE");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/tickers\/10\/$/);
    });
  });

  describe("reorderSymbols", () => {
    it("POSTs /api/watchlists/:wid/reorder/ with {order} body and returns {ok: true}", async () => {
      const api = mockApi({ "POST /api/watchlists/1/reorder/": { ok: true } });
      const res = await reorderSymbols(1, [3, 1, 2]);
      expect(res.ok).toBe(true);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/reorder\/$/);
      expect(api.calls[0].body).toEqual({ order: [3, 1, 2] });
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("POST /api/watchlists/1/reorder/", 500, "server_error", "internal error");
      const promise = reorderSymbols(1, [1, 2, 3]);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });
  });
});
