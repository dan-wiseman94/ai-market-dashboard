import { describe, expect, it } from "vitest";
import {
  fetchThreads,
  fetchThread,
  createThread,
  sendMessage,
  compareMessage,
  stopMessage,
} from "@/api/threads";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

const aiRunFixture = {
  id: 10,
  provider: "claude",
  model: "claude-sonnet-4-6",
  input_tokens: 500,
  output_tokens: 200,
  cached_tokens: 100,
  cost_usd: "0.0042",
  latency_ms: 1234,
  status: "done" as const,
  error: "",
};

const threadFixture = {
  id: 1,
  kind: "consult" as const,
  title: "Morning scan",
  profile: { id: 2, name: "Growth", default_provider: "claude", default_model: "claude-sonnet-4-6" },
  pinned_snapshot_id: 99,
  created_at: "2026-05-17T09:00:00Z",
  messages: [
    {
      id: 101,
      role: "user" as const,
      content: { text: "What do you see?" },
      status: "done" as const,
      error: "",
      created_at: "2026-05-17T09:01:00Z",
      ai_run: null,
    },
    {
      id: 102,
      role: "assistant" as const,
      content: { text: "Markets look bullish." },
      status: "done" as const,
      error: "",
      created_at: "2026-05-17T09:01:05Z",
      ai_run: aiRunFixture,
    },
  ],
};

describe("api/threads", () => {
  describe("fetchThreads", () => {
    it("GETs /api/threads/ and returns Thread[]", async () => {
      const api = mockApi({ "GET /api/threads/": [threadFixture] });
      const res = await fetchThreads();
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe(1);
      expect(res[0].kind).toBe("consult");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/threads/", 500, "server_error", "internal error");
      const promise = fetchThreads();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("returns empty array when no threads exist", async () => {
      const api = mockApi({ "GET /api/threads/": [] });
      const res = await fetchThreads();
      expect(res).toEqual([]);
      expect(api.calls).toHaveLength(1);
    });
  });

  describe("fetchThread", () => {
    it("GETs /api/threads/:id/ and returns Thread with messages including ai_run", async () => {
      const api = mockApi({ "GET /api/threads/1/": threadFixture });
      const res = await fetchThread(1);
      expect(res.id).toBe(1);
      expect(res.messages).toHaveLength(2);
      expect(res.messages[1].ai_run?.provider).toBe("claude");
      expect(res.messages[1].ai_run?.status).toBe("done");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/1\/$/);
    });

    it("throws ApiError with status 404 when thread does not exist", async () => {
      mockApiError("GET /api/threads/999/", 404, "not_found", "thread missing");
      const promise = fetchThread(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("handles thread with pinned_snapshot_id: null and profile: null", async () => {
      const nullableThread = { ...threadFixture, pinned_snapshot_id: null, profile: null };
      const api = mockApi({ "GET /api/threads/1/": nullableThread });
      const res = await fetchThread(1);
      expect(res.pinned_snapshot_id).toBeNull();
      expect(res.profile).toBeNull();
      expect(api.calls[0].method).toBe("GET");
    });
  });

  describe("createThread", () => {
    it("POSTs /api/threads/ with minimal body {kind: 'consult'}", async () => {
      const api = mockApi({ "POST /api/threads/": threadFixture });
      const body = { kind: "consult" as const };
      const res = await createThread(body);
      expect(res.id).toBe(1);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/$/);
      expect(api.calls[0].body).toEqual(body);
    });

    it("POSTs with full body including profile_id, pinned_snapshot_id, and title", async () => {
      const api = mockApi({ "POST /api/threads/": threadFixture });
      const fullBody = { kind: "chat" as const, profile_id: 2, pinned_snapshot_id: 99, title: "EOD review" };
      const res = await createThread(fullBody);
      expect(res.id).toBe(1);
      expect(api.calls[0].body).toEqual(fullBody);
    });

    it("throws ApiError with status 400 on validation error", async () => {
      mockApiError("POST /api/threads/", 400, "validation_error", "kind is required");
      const promise = createThread({ kind: "consult" });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 400, code: "validation_error" });
    });
  });

  describe("sendMessage", () => {
    it("POSTs with text and undefined overrides when no override provided", async () => {
      const api = mockApi({ "POST /api/threads/42/send/": threadFixture.messages[0] });
      await sendMessage(42, "What do you see?");
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/42\/send\/$/);
      expect(api.calls[0].body).toEqual({
        text: "What do you see?",
        override_provider: undefined,
        override_model: undefined,
      });
    });

    it("POSTs with override_provider and override_model when override is supplied", async () => {
      const api = mockApi({ "POST /api/threads/42/send/": threadFixture.messages[0] });
      await sendMessage(42, "hello", { provider: "openai", model: "gpt-5-mini" });
      expect(api.calls[0].body).toEqual({
        text: "hello",
        override_provider: "openai",
        override_model: "gpt-5-mini",
      });
    });

    it("throws ApiError with status 503 and URL contains threadId", async () => {
      mockApiError("POST /api/threads/7/send/", 503, "service_unavailable", "provider down");
      const promise = sendMessage(7, "hello");
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503, code: "service_unavailable" });
    });
  });

  describe("compareMessage", () => {
    it("POSTs to /api/threads/:id/compare/ and returns user_message_id and branches", async () => {
      const compareResponse = {
        user_message_id: 55,
        branches: [
          { provider: "claude", model: "claude-sonnet-4-6", task_id: "task-abc" },
          { provider: "openai", model: "gpt-5-mini", task_id: "task-def" },
        ],
      };
      const api = mockApi({ "POST /api/threads/3/compare/": compareResponse });
      const res = await compareMessage(3, "Compare this", [
        { provider: "claude", model: "claude-sonnet-4-6" },
        { provider: "openai", model: "gpt-5-mini" },
      ]);
      expect(res.user_message_id).toBe(55);
      expect(res.branches).toHaveLength(2);
      expect(res.branches[0].task_id).toBe("task-abc");
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/3\/compare\/$/);
      expect(api.calls[0].body).toEqual({
        text: "Compare this",
        branches: [
          { provider: "claude", model: "claude-sonnet-4-6" },
          { provider: "openai", model: "gpt-5-mini" },
        ],
      });
    });

    it("throws ApiError with status 500 and URL contains threadId", async () => {
      mockApiError("POST /api/threads/3/compare/", 500, "server_error", "internal error");
      const promise = compareMessage(3, "Compare this", [{ provider: "claude", model: "claude-opus-4-5" }]);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("sends empty branches array when no branches provided", async () => {
      const compareResponse = { user_message_id: 60, branches: [] };
      const api = mockApi({ "POST /api/threads/3/compare/": compareResponse });
      const res = await compareMessage(3, "No branches", []);
      expect(res.branches).toHaveLength(0);
      expect(api.calls[0].body).toEqual({ text: "No branches", branches: [] });
    });
  });

  describe("stopMessage", () => {
    it("POSTs to /api/threads/:id/stop/:msgId/ and returns {ok: true}", async () => {
      const api = mockApi({ "POST /api/threads/5/stop/200/": { ok: true } });
      const res = await stopMessage(5, 200);
      expect(res.ok).toBe(true);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/5\/stop\/200\/$/);
    });

    it("throws ApiError with status 404 when message does not exist", async () => {
      mockApiError("POST /api/threads/5/stop/999/", 404, "not_found", "message not found");
      const promise = stopMessage(5, 999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("sends no request body (apiPost called without body argument)", async () => {
      const api = mockApi({ "POST /api/threads/5/stop/200/": { ok: true } });
      await stopMessage(5, 200);
      expect(api.calls[0].body).toBeUndefined();
    });
  });
});
