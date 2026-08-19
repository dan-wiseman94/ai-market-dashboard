import { describe, expect, it } from "vitest";
import {
  fetchAiModels,
  fetchProviderConfigs,
  fetchAiUsage,
  upsertProviderConfig,
} from "@/api/ai";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// Note: setup.ts has a global afterEach that calls vi.unstubAllGlobals(),
// so each test starts with a fresh fetch.

const claudeModel = {
  id: "claude-opus-4-8",
  name: "Claude Opus 4.8",
  provider: "claude",
  input_per_mtok: 15,
  output_per_mtok: 75,
  cached_per_mtok: 1.5,
  context_window: 1_000_000,
  supports_vision: true,
};

const claudeProviderConfig = {
  provider: "claude" as const,
  base_url: "",
  default_model: "claude-opus-4-8",
  enabled: true,
  supports_vision: true,
  daily_cost_cap_usd: "5",
  monthly_cost_cap_usd: null,
  api_key_present: true,
};
const localProviderConfig = {
  provider: "local" as const,
  base_url: "http://localhost:11434",
  default_model: "llama3",
  enabled: true,
  supports_vision: false,
  daily_cost_cap_usd: "1",
  monthly_cost_cap_usd: null,
  api_key_present: false,
};

describe("api/ai", () => {
  describe("fetchAiModels", () => {
    it("GETs models with no provider filter by default", async () => {
      const api = mockApi({ "GET /api/schwab/models/": { models: [claudeModel] } });
      const res = await fetchAiModels();
      expect(res.models).toHaveLength(1);
      expect(res.models[0].id).toBe("claude-opus-4-8");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/schwab\/models\/$/);
    });

    it("encodes provider query param when passed", async () => {
      const api = mockApi({ "GET /api/schwab/models/": { models: [] } });
      await fetchAiModels("open ai");
      expect(api.calls[0].url).toMatch(/provider=open%20ai/);
    });

    it("propagates ApiError on non-2xx", async () => {
      mockApiError("GET /api/schwab/models/", 500, "server_error", "boom");
      const promise = fetchAiModels();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error", message: "boom" });
    });
  });

  describe("fetchProviderConfigs", () => {
    it("returns array of ProviderConfig on 200", async () => {
      mockApi({ "GET /api/schwab/providers/": [claudeProviderConfig] });
      const res = await fetchProviderConfigs();
      expect(res).toEqual([expect.objectContaining({ provider: "claude" })]);
    });

    it("throws ApiError on 503", async () => {
      mockApiError("GET /api/schwab/providers/", 503);
      const promise = fetchProviderConfigs();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503 });
    });
  });

  describe("upsertProviderConfig", () => {
    it("PATCHes when the provider exists", async () => {
      const api = mockApi({
        "PATCH /api/schwab/providers/claude/": { ...claudeProviderConfig, enabled: false },
      });
      const res = await upsertProviderConfig("claude", { enabled: false });
      expect(res.enabled).toBe(false);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("PATCH");
      expect(api.calls[0].body).toEqual({ enabled: false });
      expect(api.calls[0].url).toMatch(/\/api\/schwab\/providers\/claude\/$/);
    });

    it("falls back to POST when PATCH returns 404", async () => {
      const api = mockApi({
        "PATCH /api/schwab/providers/local/": { status: 404, code: "not_found", message: "missing" },
        "POST /api/schwab/providers/": localProviderConfig,
      });
      const res = await upsertProviderConfig("local", { base_url: "http://localhost:11434" });
      expect(res.provider).toBe("local");
      expect(api.calls.map((c) => c.method)).toEqual(["PATCH", "POST"]);
      expect(api.calls[1].body).toEqual({ provider: "local", base_url: "http://localhost:11434" });
    });

    it("re-throws non-404 ApiError from PATCH without falling back", async () => {
      const api = mockApi({
        "PATCH /api/schwab/providers/claude/": { status: 500, code: "server_error", message: "boom" },
      });
      await expect(upsertProviderConfig("claude", {})).rejects.toBeInstanceOf(ApiError);
      expect(api.calls.map((c) => c.method)).toEqual(["PATCH"]);
    });
  });

  describe("fetchAiUsage", () => {
    it("returns the shaped usage object", async () => {
      const api = mockApi({ "GET /api/schwab/usage/": { today: { claude: "0.0012", openai: "0.0000" } } });
      const res = await fetchAiUsage();
      expect(res.today.claude).toBe("0.0012");
      expect(res.today.openai).toBe("0.0000");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
    });

    it("propagates ApiError when the endpoint fails", async () => {
      mockApiError("GET /api/schwab/usage/", 502, "bad_gateway", "upstream");
      await expect(fetchAiUsage()).rejects.toBeInstanceOf(ApiError);
    });
  });
});
