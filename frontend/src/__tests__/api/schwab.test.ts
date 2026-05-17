import { describe, expect, it } from "vitest";
import { fetchSchwabStatus, fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// ---- fetchSchwabStatus ----

describe("api/schwab", () => {
  describe("fetchSchwabStatus", () => {
    it("GETs /api/schwab/status/ and returns connected status with expires_at", async () => {
      const api = mockApi({
        "GET /api/schwab/status/": { connected: true, expires_at: "2026-12-31T00:00:00Z" },
      });
      const res = await fetchSchwabStatus();
      expect(res.connected).toBe(true);
      expect(res.expires_at).toBe("2026-12-31T00:00:00Z");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/schwab\/status\/$/);
    });

    it("GETs /api/schwab/status/ and handles disconnected state with null expires_at", async () => {
      const api = mockApi({
        "GET /api/schwab/status/": { connected: false, expires_at: null },
      });
      const res = await fetchSchwabStatus();
      expect(res.connected).toBe(false);
      expect(res.expires_at).toBeNull();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
    });

    it("throws ApiError with status 503 on service unavailable", async () => {
      mockApiError("GET /api/schwab/status/", 503, "service_unavailable", "schwab down");
      const promise = fetchSchwabStatus();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503, code: "service_unavailable" });
    });
  });

  // ---- fetchSchwabAuthorizeUrl ----

  describe("fetchSchwabAuthorizeUrl", () => {
    it("GETs /api/schwab/authorize/ and returns the authorize url", async () => {
      const api = mockApi({
        "GET /api/schwab/authorize/": {
          url: "https://api.schwabapi.com/v1/oauth/authorize?client_id=abc&redirect_uri=https%3A%2F%2Fexample.com",
        },
      });
      const res = await fetchSchwabAuthorizeUrl();
      expect(res.url).toBe(
        "https://api.schwabapi.com/v1/oauth/authorize?client_id=abc&redirect_uri=https%3A%2F%2Fexample.com",
      );
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/schwab\/authorize\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/schwab/authorize/", 500, "server_error", "internal error");
      const promise = fetchSchwabAuthorizeUrl();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("passes the url back verbatim without normalization", async () => {
      const rawUrl =
        "https://api.schwabapi.com/v1/oauth/authorize?client_id=xyz&scope=readonly&state=abc123";
      mockApi({ "GET /api/schwab/authorize/": { url: rawUrl } });
      const res = await fetchSchwabAuthorizeUrl();
      expect(res.url).toBe(rawUrl);
    });
  });
});
