import { describe, expect, it } from "vitest";
import {
  listSchedules,
  createSchedule,
  patchSchedule,
  deleteSchedule,
  runScheduleNow,
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getMarketStatus,
} from "@/api/observer";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

const scheduleFixture = {
  id: 7,
  name: "Morning Brief",
  profile: 3,
  enabled: true,
  market_hours_only: true,
  objective_template: "Summarise overnight moves",
  override_provider: "claude",
  override_model: "claude-opus-4-8",
  default_includes: ["quotes", "news"],
  default_watchlist_tickers: ["AAPL", "TSLA"],
  mode: "full" as const,
  structured: false,
  use_batch: false,
  last_batch_id: "",
  last_fired_at: "2026-05-17T09:30:00Z",
  cron_display: "0 9 * * 1-5",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-17T09:30:00Z",
};

const notificationFixture = {
  id: 42,
  kind: "observer_done" as const,
  title: "Observer fired",
  body: "Morning Brief completed successfully",
  link: "/threads/99",
  meta: { schedule_id: 7 },
  read_at: null,
  created_at: "2026-05-17T09:31:00Z",
};

const marketStatusFixture = {
  is_open: true,
  next_open: "2026-05-19T13:30:00Z",
  next_close: "2026-05-17T20:00:00Z",
};

describe("api/observer", () => {
  describe("listSchedules", () => {
    it("GETs /api/observer/schedules/ and returns schedule array", async () => {
      const api = mockApi({ "GET /api/observer/schedules/": [scheduleFixture] });
      const res = await listSchedules();
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe(7);
      expect(res[0].name).toBe("Morning Brief");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("GET /api/observer/schedules/", 500, "server_error", "internal error");
      const promise = listSchedules();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("returns an empty array when no schedules exist", async () => {
      mockApi({ "GET /api/observer/schedules/": [] });
      const res = await listSchedules();
      expect(res).toEqual([]);
    });
  });

  describe("createSchedule", () => {
    it("POSTs to /api/observer/schedules/ and returns the created schedule", async () => {
      const api = mockApi({ "POST /api/observer/schedules/": scheduleFixture });
      const body = {
        name: "Morning Brief",
        profile: 3,
        cron: "0 9 * * 1-5",
        enabled: true,
        market_hours_only: true,
        objective_template: "Summarise overnight moves",
        override_provider: "claude",
        override_model: "claude-opus-4-8",
        default_includes: ["quotes", "news"],
        default_watchlist_tickers: ["AAPL", "TSLA"],
        mode: "full" as const,
        structured: false,
        use_batch: false,
      };
      const res = await createSchedule(body);
      expect(res.id).toBe(7);
      expect(res.name).toBe("Morning Brief");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/$/);
      expect(api.calls[0].body).toEqual(body);
    });

    it("throws ApiError with status 503 on service unavailable", async () => {
      mockApiError("POST /api/observer/schedules/", 503, "unavailable", "service down");
      const promise = createSchedule({ name: "Test", profile: 1, cron: "0 * * * *" });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503, code: "unavailable" });
    });

    it("sends full CreateScheduleBody fields in the request", async () => {
      const api = mockApi({ "POST /api/observer/schedules/": scheduleFixture });
      const fullBody = {
        name: "Full Test",
        profile: 5,
        cron: "30 14 * * *",
        enabled: false,
        market_hours_only: false,
        objective_template: "Afternoon check",
        override_provider: "openai",
        override_model: "gpt-4o",
        default_includes: ["quotes", "chain", "ohlc"],
        default_watchlist_tickers: ["SPY", "QQQ", "IWM"],
        mode: "diff" as const,
        structured: true,
        use_batch: true,
      };
      await createSchedule(fullBody);
      expect(api.calls[0].body).toEqual(fullBody);
    });
  });

  describe("patchSchedule", () => {
    it("PATCHes /api/observer/schedules/:id/ and returns updated schedule", async () => {
      const api = mockApi({ "PATCH /api/observer/schedules/7/": { ...scheduleFixture, enabled: false } });
      const res = await patchSchedule(7, { enabled: false });
      expect(res.enabled).toBe(false);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("PATCH");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/7\/$/);
    });

    it("throws ApiError with status 401 when unauthenticated", async () => {
      mockApiError("PATCH /api/observer/schedules/7/", 401, "unauthorized", "login required");
      const promise = patchSchedule(7, { enabled: false });
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    });

    it("sends only the partial body fields and embeds the id in the URL", async () => {
      const api = mockApi({ "PATCH /api/observer/schedules/99/": scheduleFixture });
      await patchSchedule(99, { name: "Renamed", enabled: true });
      expect(api.calls[0].body).toEqual({ name: "Renamed", enabled: true });
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/99\/$/);
    });
  });

  describe("deleteSchedule", () => {
    it("DELETEs /api/observer/schedules/:id/ and resolves on 204", async () => {
      const api = mockApi({ "DELETE /api/observer/schedules/42/": undefined });
      const res = await deleteSchedule(42);
      expect(res).toBeUndefined();
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("DELETE");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/42\/$/);
    });

    it("throws ApiError with status 404 when schedule does not exist", async () => {
      mockApiError("DELETE /api/observer/schedules/999/", 404, "not_found", "schedule missing");
      const promise = deleteSchedule(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("embeds the id correctly for different schedule ids", async () => {
      const api = mockApi({ "DELETE /api/observer/schedules/1/": undefined });
      await deleteSchedule(1);
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/1\/$/);
    });
  });

  describe("runScheduleNow", () => {
    it("POSTs to /api/observer/schedules/:id/run-now/ with empty body", async () => {
      const api = mockApi({ "POST /api/observer/schedules/7/run-now/": undefined });
      await runScheduleNow(7);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/7\/run-now\/$/);
      expect(api.calls[0].body).toEqual({});
    });

    it("throws ApiError with status 500 when the task fails to dispatch", async () => {
      mockApiError("POST /api/observer/schedules/7/run-now/", 500, "dispatch_error", "celery unavailable");
      const promise = runScheduleNow(7);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "dispatch_error" });
    });

    it("embeds the schedule id in the URL", async () => {
      const api = mockApi({ "POST /api/observer/schedules/55/run-now/": undefined });
      await runScheduleNow(55);
      expect(api.calls[0].url).toMatch(/\/api\/observer\/schedules\/55\/run-now\/$/);
    });
  });

  describe("listNotifications", () => {
    it("GETs /api/observer/notifications/?limit=50 without unread param by default", async () => {
      const api = mockApi({ "GET /api/observer/notifications/": [notificationFixture] });
      const res = await listNotifications();
      expect(res).toEqual([notificationFixture]);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toContain("limit=50");
      expect(api.calls[0].url).not.toContain("unread=true");
    });

    it("throws ApiError with status 403 when access is denied", async () => {
      mockApiError("GET /api/observer/notifications/", 403, "forbidden", "access denied");
      const promise = listNotifications();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 403, code: "forbidden" });
    });

    it("appends &unread=true to URL when unread=true is passed", async () => {
      const api = mockApi({ "GET /api/observer/notifications/": [] });
      await listNotifications(true);
      expect(api.calls[0].url).toContain("&unread=true");
    });
  });

  describe("markNotificationRead", () => {
    it("POSTs to /api/observer/notifications/:id/read/ with empty body", async () => {
      const api = mockApi({
        "POST /api/observer/notifications/42/read/": { ...notificationFixture, read_at: "2026-05-17T10:00:00Z" },
      });
      const res = await markNotificationRead(42);
      expect(res.id).toBe(42);
      expect(res.read_at).toBe("2026-05-17T10:00:00Z");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/notifications\/42\/read\/$/);
      expect(api.calls[0].body).toEqual({});
    });

    it("throws ApiError with status 404 when notification does not exist", async () => {
      mockApiError("POST /api/observer/notifications/999/read/", 404, "not_found", "notification missing");
      const promise = markNotificationRead(999);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 404, code: "not_found" });
    });

    it("embeds the notification id in the URL", async () => {
      const api = mockApi({ "POST /api/observer/notifications/77/read/": notificationFixture });
      await markNotificationRead(77);
      expect(api.calls[0].url).toMatch(/\/api\/observer\/notifications\/77\/read\/$/);
    });
  });

  describe("markAllNotificationsRead", () => {
    it("POSTs to /api/observer/notifications/mark-all-read/ and returns {ok:true}", async () => {
      const api = mockApi({ "POST /api/observer/notifications/mark-all-read/": { ok: true } });
      const res = await markAllNotificationsRead();
      expect(res).toEqual({ ok: true });
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("POST");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/notifications\/mark-all-read\/$/);
    });

    it("throws ApiError with status 500 on server error", async () => {
      mockApiError("POST /api/observer/notifications/mark-all-read/", 500, "server_error", "boom");
      const promise = markAllNotificationsRead();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 500, code: "server_error" });
    });

    it("hits the exact URL with no extra query params", async () => {
      const api = mockApi({ "POST /api/observer/notifications/mark-all-read/": { ok: true } });
      await markAllNotificationsRead();
      expect(api.calls[0].url).toBe("/api/observer/notifications/mark-all-read/");
    });
  });

  describe("getMarketStatus", () => {
    it("GETs /api/observer/market-status/ and returns market status", async () => {
      const api = mockApi({ "GET /api/observer/market-status/": marketStatusFixture });
      const res = await getMarketStatus();
      expect(res.is_open).toBe(true);
      expect(res.next_open).toBe("2026-05-19T13:30:00Z");
      expect(res.next_close).toBe("2026-05-17T20:00:00Z");
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/observer\/market-status\/$/);
    });

    it("throws ApiError with status 503 when the market status service is down", async () => {
      mockApiError("GET /api/observer/market-status/", 503, "unavailable", "calendar service down");
      const promise = getMarketStatus();
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ status: 503, code: "unavailable" });
    });

    it("handles null next_open and next_close when market is mid-session with no future events", async () => {
      const api = mockApi({
        "GET /api/observer/market-status/": { is_open: false, next_open: null, next_close: null },
      });
      const res = await getMarketStatus();
      expect(res.is_open).toBe(false);
      expect(res.next_open).toBeNull();
      expect(res.next_close).toBeNull();
      expect(api.calls[0].url).toMatch(/\/api\/observer\/market-status\/$/);
    });
  });
});
