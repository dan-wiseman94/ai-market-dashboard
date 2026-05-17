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
  symbols: [symbolFixture],
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

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/watchlists/", 500, "server_error", "internal error");
      const promise = fetchWatchlists();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("returns empty array when no watchlists exist", async () => {
      const api = mockApi({ "GET /api/watchlists/": [] });
      const res = await fetchWatchlists();
      expect(res).toEqual([]);
      expect(api.calls).toHaveLength(1);
    });
  });

  describe("fetchWatchlist", () => {
    it("GETs /api/watchlists/:id/ and returns Watchlist with symbols", async () => {
      const api = mockApi({ "GET /api/watchlists/1/": watchlistFixture });
      const res = await fetchWatchlist(1);
      expect(res.id).toBe(1);
      expect(res.symbols).toHaveLength(1);
      expect(res.symbols[0].ticker).toBe("AAPL");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/$/);
    });

    it("throws ApiError with status 404 when watchlist does not exist", async () => {
      mockApiError("GET /api/watchlists/999/", 404, "not_found", "watchlist missing");
      const promise = fetchWatchlist(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("URL contains the requested id", async () => {
      const api = mockApi({ "GET /api/watchlists/42/": { ...watchlistFixture, id: 42 } });
      const res = await fetchWatchlist(42);
      expect(res.id).toBe(42);
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/42\/$/);
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

    it("throws ApiError with status 400 on validation error", async () => {
      mockApiError("POST /api/watchlists/", 400, "validation_error", "name is required");
      const promise = createWatchlist("");
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
    });

    it("sends exactly {name} body with no extra fields", async () => {
      const api = mockApi({ "POST /api/watchlists/": watchlistFixture });
      await createWatchlist("My List");
      expect(api.calls[0].body).toEqual({ name: "My List" });
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

    it("throws ApiError with status 401 when not authenticated", async () => {
      mockApiError("PATCH /api/watchlists/1/", 401, "unauthorized", "login required");
      const promise = renameWatchlist(1, "New Name");
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    });

    it("sends partial {name} body only, URL contains id", async () => {
      const api = mockApi({ "PATCH /api/watchlists/7/": { ...watchlistFixture, id: 7, name: "Partial" } });
      await renameWatchlist(7, "Partial");
      expect(api.calls[0].body).toEqual({ name: "Partial" });
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/7\/$/);
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

    it("throws ApiError with status 404 when watchlist does not exist", async () => {
      mockApiError("DELETE /api/watchlists/999/", 404, "not_found", "watchlist missing");
      const promise = deleteWatchlist(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("DELETE /api/watchlists/1/", 500, "server_error", "internal error");
      const promise = deleteWatchlist(1);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });
  });

  describe("addSymbol", () => {
    it("POSTs /api/watchlists/:wid/symbols/ with {ticker} body and returns WatchlistSymbol", async () => {
      const api = mockApi({ "POST /api/watchlists/1/symbols/": symbolFixture });
      const res = await addSymbol(1, "AAPL");
      expect(res.id).toBe(10);
      expect(res.ticker).toBe("AAPL");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/symbols\/$/);
      expect(api.calls[0].body).toEqual({ ticker: "AAPL" });
    });

    it("throws ApiError with status 400 on invalid ticker", async () => {
      mockApiError("POST /api/watchlists/1/symbols/", 400, "validation_error", "invalid ticker");
      const promise = addSymbol(1, "");
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
    });

    it("URL contains watchlist id but not symbol id", async () => {
      const api = mockApi({ "POST /api/watchlists/5/symbols/": { ...symbolFixture, id: 20, ticker: "MSFT" } });
      await addSymbol(5, "MSFT");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/5\/symbols\/$/);
      expect(api.calls[0].url).not.toMatch(/\/symbols\/20\//);
    });
  });

  describe("removeSymbol", () => {
    it("DELETEs /api/watchlists/:wid/symbols/:sid/ and resolves on 204", async () => {
      const api = mockApi({ "DELETE /api/watchlists/1/symbols/10/": undefined });
      await expect(removeSymbol(1, 10)).resolves.not.toThrow();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("DELETE");
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/1\/symbols\/10\/$/);
    });

    it("throws ApiError with status 404 when symbol does not exist", async () => {
      mockApiError("DELETE /api/watchlists/1/symbols/999/", 404, "not_found", "symbol missing");
      const promise = removeSymbol(1, 999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("URL has both wid and sid", async () => {
      const api = mockApi({ "DELETE /api/watchlists/3/symbols/7/": undefined });
      await removeSymbol(3, 7);
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/3\/symbols\/7\/$/);
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

    it("sends {order: [3,1,2]} body exactly and URL contains wid", async () => {
      const api = mockApi({ "POST /api/watchlists/9/reorder/": { ok: true } });
      await reorderSymbols(9, [3, 1, 2]);
      expect(api.calls[0].body).toEqual({ order: [3, 1, 2] });
      expect(api.calls[0].url).toMatch(/\/api\/watchlists\/9\/reorder\/$/);
    });
  });
});
