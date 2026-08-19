import { describe, expect, it } from "vitest";
import {
  fetchProfiles,
  fetchProfile,
  createProfile,
  updateProfile,
  deleteProfile,
} from "@/api/profiles";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

const profileFixture = {
  id: 1,
  name: "Swing Trader",
  style: "swing",
  default_includes: ["quotes", "ohlc", "news"],
  default_provider: "claude",
  default_model: "claude-opus-4-8",
  active: true,
};

describe("api/profiles", () => {
  describe("fetchProfiles", () => {
    it("GETs /api/profiles/ and returns profile array", async () => {
      const api = mockApi({ "GET /api/profiles/": [profileFixture] });
      const res = await fetchProfiles();
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe(1);
      expect(res[0].name).toBe("Swing Trader");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/profiles/", 500, "server_error", "internal error");
      const promise = fetchProfiles();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("returns an empty array when no profiles exist", async () => {
      mockApi({ "GET /api/profiles/": [] });
      const res = await fetchProfiles();
      expect(res).toEqual([]);
    });
  });

  describe("fetchProfile", () => {
    it("GETs /api/profiles/:id/ and returns the profile", async () => {
      const api = mockApi({ "GET /api/profiles/1/": profileFixture });
      const res = await fetchProfile(1);
      expect(res.id).toBe(1);
      expect(res.name).toBe("Swing Trader");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/1\/$/);
    });

    it("throws ApiError with status 404 when profile does not exist", async () => {
      mockApiError("GET /api/profiles/999/", 404, "not_found", "profile missing");
      const promise = fetchProfile(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("embeds the id in the URL", async () => {
      const api = mockApi({ "GET /api/profiles/42/": profileFixture });
      await fetchProfile(42);
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/42\/$/);
    });
  });

  describe("createProfile", () => {
    it("POSTs to /api/profiles/ and returns the created profile", async () => {
      const api = mockApi({ "POST /api/profiles/": profileFixture });
      const body = {
        name: "Swing Trader",
        style: "swing",
        default_includes: ["quotes", "ohlc", "news"],
        default_provider: "claude",
        default_model: "claude-opus-4-8",
        active: true,
      };
      const res = await createProfile(body);
      expect(res.id).toBe(1);
      expect(res.name).toBe("Swing Trader");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/$/);
      expect(api.calls[0].body).toEqual(body);
    });

    it("throws ApiError with status 400 on validation error", async () => {
      mockApiError("POST /api/profiles/", 400, "validation_error", "name is required");
      const promise = createProfile({ style: "day" });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
    });

    it("sends full body shape in the request", async () => {
      const api = mockApi({ "POST /api/profiles/": profileFixture });
      const fullBody = {
        name: "Day Trader",
        style: "day",
        default_includes: ["quotes", "chain"],
        default_provider: "openai",
        default_model: "gpt-4o",
        active: false,
      };
      await createProfile(fullBody);
      expect(api.calls[0].body).toEqual(fullBody);
    });
  });

  describe("updateProfile", () => {
    it("PATCHes /api/profiles/:id/ and returns the updated profile", async () => {
      const updated = { ...profileFixture, name: "Renamed" };
      const api = mockApi({ "PATCH /api/profiles/1/": updated });
      const res = await updateProfile(1, { name: "Renamed" });
      expect(res.name).toBe("Renamed");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("PATCH");
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/1\/$/);
    });

    it("throws ApiError with status 401 when unauthenticated", async () => {
      mockApiError("PATCH /api/profiles/1/", 401, "unauthorized", "login required");
      const promise = updateProfile(1, { active: false });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    });

    it("sends only the partial body fields and embeds the id in the URL", async () => {
      const api = mockApi({ "PATCH /api/profiles/7/": profileFixture });
      await updateProfile(7, { active: false, default_model: "claude-haiku-4-5" });
      expect(api.calls[0].body).toEqual({ active: false, default_model: "claude-haiku-4-5" });
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/7\/$/);
    });
  });

  describe("deleteProfile", () => {
    it("DELETEs /api/profiles/:id/ and resolves on 204", async () => {
      const api = mockApi({ "DELETE /api/profiles/1/": undefined });
      const res = await deleteProfile(1);
      expect(res).toBeUndefined();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("DELETE");
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/1\/$/);
    });

    it("throws ApiError with status 503 on service error", async () => {
      mockApiError("DELETE /api/profiles/1/", 503, "unavailable", "service down");
      const promise = deleteProfile(1);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503, code: "unavailable" });
    });

    it("embeds the id correctly in the URL", async () => {
      const api = mockApi({ "DELETE /api/profiles/55/": undefined });
      await deleteProfile(55);
      expect(api.calls[0].url).toMatch(/\/api\/profiles\/55\/$/);
    });
  });
});
