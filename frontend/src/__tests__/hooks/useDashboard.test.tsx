import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, afterEach } from "vitest";
import { useDashboard } from "@/hooks/useDashboard";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";

const FIXTURE = {
  theses: [
    {
      id: 1,
      ticker: "AAPL",
      direction: "bullish",
      conviction: 4,
      entry: 170.0,
      target: 200.0,
      invalidation: 155.0,
      current: 185.0,
      pct_to_target: 8.11,
      pct_to_invalidation: -16.22,
    },
  ],
  events: {
    earnings: [
      {
        kind: "earnings",
        ticker: "AAPL",
        title: "AAPL earnings (BMO)",
        event_time: "2026-06-01T13:00:00+00:00",
        days_until: 2,
        when_hint: "bmo",
        impact: "high",
        detail: {},
      },
    ],
    macro: [],
  },
  observer: {
    enabled_schedules: 3,
    runs_today: 5,
  },
  triggers: {
    armed_count: 7,
    latest_firings: [
      {
        id: 42,
        trigger_id: 10,
        trigger_name: "AAPL breakout",
        fired_at: "2026-05-30T09:45:00Z",
        cost_capped: false,
      },
    ],
  },
  briefing: {
    id: 99,
    status: "ready",
    created_at: "2026-05-30T08:00:00Z",
    scheduled_date: "2026-05-30",
  },
};

afterEach(() => {
  import("vitest").then(({ vi }) => vi.unstubAllGlobals());
});

describe("useDashboard", () => {
  it("fetches /api/dashboard/ and returns full payload", async () => {
    const { calls } = mockApi({ "GET /api/dashboard/": FIXTURE });
    const { result } = renderHook(() => useDashboard(), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(calls[0].url).toContain("/api/dashboard/");
    expect(calls[0].method).toBe("GET");

    const data = result.current.data!;
    expect(data.theses).toHaveLength(1);
    expect(data.theses[0].ticker).toBe("AAPL");
    expect(data.theses[0].pct_to_target).toBe(8.11);

    expect(data.observer.enabled_schedules).toBe(3);
    expect(data.observer.runs_today).toBe(5);

    expect(data.triggers.armed_count).toBe(7);
    expect(data.triggers.latest_firings[0].trigger_name).toBe("AAPL breakout");

    expect(data.briefing?.status).toBe("ready");
    expect(data.briefing?.id).toBe(99);

    expect(data.events.earnings[0].ticker).toBe("AAPL");
    expect(data.events.earnings[0].days_until).toBe(2);
  });

  it("returns null briefing when backend sends null", async () => {
    mockApi({ "GET /api/dashboard/": { ...FIXTURE, briefing: null } });
    const { result } = renderHook(() => useDashboard(), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.briefing).toBeNull();
  });

  it("isError on fetch failure", async () => {
    mockApi({ "GET /api/dashboard/": { status: 500, code: "error", message: "oops" } });
    const { result } = renderHook(() => useDashboard(), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses query key ['dashboard']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/dashboard/": FIXTURE });
    renderHook(() => useDashboard(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["dashboard"]);
    });
  });
});
