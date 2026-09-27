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

// The list endpoint returns light rows (no messages) inside a paginated envelope.
const threadListRowFixture = {
  id: 1,
  kind: "consult" as const,
  title: "Morning scan",
  profile: { id: 2, name: "Growth", default_provider: "claude", default_model: "claude-sonnet-4-6" },
  pinned_snapshot_id: 99,
  created_at: "2026-05-17T09:00:00Z",
  message_count: 2,
};

describe("api/threads", () => {
  describe("fetchThreads", () => {
    it("GETs /api/threads/ and returns the unwrapped paginated rows", async () => {
      const api = mockApi({ "GET /api/threads/": { results: [threadListRowFixture] } });
      const res = await fetchThreads();
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe(1);
      expect(res[0].kind).toBe("consult");
      expect(res[0].message_count).toBe(2);
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
  });

  describe("stopMessage", () => {
    it("POSTs to /api/threads/:id/stop/:msgId/ and returns {ok: true}", async () => {
      const api = mockApi({ "POST /api/threads/5/stop/200/": { ok: true } });
      const res = await stopMessage(5, 200);
      expect(res.ok).toBe(true);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/threads\/5\/stop\/200\/$/);
    });

    it("sends no request body (apiPost called without body argument)", async () => {
      const api = mockApi({ "POST /api/threads/5/stop/200/": { ok: true } });
      await stopMessage(5, 200);
      expect(api.calls[0].body).toBeUndefined();
    });
  });
});
