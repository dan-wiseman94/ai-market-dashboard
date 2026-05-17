import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useCreateSchedule,
  useDeleteSchedule,
  useRunSchedule,
  useSchedules,
  useToggleSchedule,
} from "@/hooks/useSchedules";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const scheduleFixture = {
  id: 3,
  name: "Morning scan",
  profile: 1,
  enabled: true,
  market_hours_only: true,
  objective_template: "Summarise premarket",
  override_provider: "",
  override_model: "",
  default_includes: [],
  default_watchlist_tickers: [],
  mode: "full",
  structured: false,
  use_batch: false,
  last_batch_id: "",
  last_fired_at: null,
  cron_display: "0 9 * * 1-5",
  created_at: "2026-05-17T00:00:00Z",
  updated_at: "2026-05-17T00:00:00Z",
};

describe("useSchedules", () => {
  it("returns schedules on success", async () => {
    mockApi({ "GET /api/observer/schedules/": [scheduleFixture] });
    const { result } = renderHook(() => useSchedules(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("Morning scan");
  });

  it("isError on fetch failure", async () => {
    mockApiError("GET /api/observer/schedules/", 500);
    const { result } = renderHook(() => useSchedules(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useCreateSchedule", () => {
  it("sends body and invalidates ['schedules']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/observer/schedules/": scheduleFixture });
    const { result } = renderHook(() => useCreateSchedule(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ name: "Morning scan", profile: 1, cron: "0 9 * * 1-5" });
    });
    expect(calls[0].body).toMatchObject({ name: "Morning scan", profile: 1, cron: "0 9 * * 1-5" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["schedules"] });
  });
});

describe("useToggleSchedule", () => {
  it("PATCHes with {enabled} and URL contains id; invalidates ['schedules']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    const { calls } = mockApi({ "PATCH /api/observer/schedules/3/": scheduleFixture });
    const { result } = renderHook(() => useToggleSchedule(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: 3, enabled: false });
    });
    expect(calls[0].url).toContain("/api/observer/schedules/3/");
    expect(calls[0].body).toMatchObject({ enabled: false });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["schedules"] });
  });
});

describe("useDeleteSchedule", () => {
  it("sends DELETE and invalidates ['schedules']", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({ "DELETE /api/observer/schedules/3/": undefined });
    const { result } = renderHook(() => useDeleteSchedule(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(3);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["schedules"] });
  });
});

describe("useRunSchedule", () => {
  it("POSTs to run-now endpoint and does NOT invalidate schedules", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({ "POST /api/observer/schedules/3/run-now/": undefined });
    const { result } = renderHook(() => useRunSchedule(), {
      wrapper: hookWrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync(3);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
