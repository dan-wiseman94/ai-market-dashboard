import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  useCostsToday,
  useCostsSummary,
  useCostsCaps,
  useCostsSnapshot,
} from "@/hooks/useCosts";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const todayFixture = {
  total_usd: "1.23",
  by_provider: [
    { provider: "claude", cost_usd: "1.23", runs: 5, input_tokens: 1000, output_tokens: 500, cached_tokens: 200 },
  ],
};

const summaryFixture = {
  total: "5.00",
  by_provider: [],
  by_model: [],
  by_thread: [],
  daily: [],
};

const capsFixture = [
  {
    provider: "claude",
    daily: { cap: "10.00", spent: "1.23", pct: 12.3 },
    monthly: { cap: "100.00", spent: "15.00", pct: 15.0 },
  },
];

const snapshotBreakdownFixture = [
  { section: "quotes", payload_tokens: 200, cost_share_usd: "0.05" },
];

describe("useCostsToday", () => {
  it("returns today's costs on success and starts in loading state", async () => {
    mockApi({ "GET /api/costs/today/": todayFixture });
    const { result } = renderHook(() => useCostsToday(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_usd).toBe("1.23");
    expect(result.current.data?.by_provider).toHaveLength(1);
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/costs/today/", 500);
    const { result } = renderHook(() => useCostsToday(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key ['costs-today']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/costs/today/": todayFixture });
    renderHook(() => useCostsToday(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["costs-today"]);
    });
  });
});

describe("useCostsSummary", () => {
  it("returns summary data and key includes range fields", async () => {
    const range = { from: "2026-05-01", to: "2026-05-17" };
    mockApi({ "GET /api/costs/summary": summaryFixture });
    const { result } = renderHook(() => useCostsSummary(range), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe("5.00");
  });

  it("uses stable query key including range.from and range.to", async () => {
    const client = newQueryClient();
    const range = { from: "2026-05-01", to: "2026-05-17" };
    mockApi({ "GET /api/costs/summary": summaryFixture });
    renderHook(() => useCostsSummary(range), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["costs-summary", "2026-05-01", "2026-05-17"]);
    });
  });
});

describe("useCostsCaps", () => {
  it("returns caps on success", async () => {
    mockApi({ "GET /api/costs/caps": capsFixture });
    const { result } = renderHook(() => useCostsCaps(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].provider).toBe("claude");
  });

  it("uses stable query key ['costs-caps']", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/costs/caps": capsFixture });
    renderHook(() => useCostsCaps(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["costs-caps"]);
    });
  });
});

describe("useCostsSnapshot", () => {
  it("returns snapshot breakdown when id is provided", async () => {
    mockApi({ "GET /api/costs/snapshot/42": snapshotBreakdownFixture });
    const { result } = renderHook(() => useCostsSnapshot(42), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].section).toBe("quotes");
  });

  it("is disabled and does not fetch when id is null", async () => {
    const mock = mockApi({ "GET /api/costs/snapshot/": snapshotBreakdownFixture });
    const { result } = renderHook(() => useCostsSnapshot(null), { wrapper: hookWrapper() });
    // Wait a tick for any potential (erroneous) fetch
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("uses query key including snapshotId", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/costs/snapshot/7": snapshotBreakdownFixture });
    renderHook(() => useCostsSnapshot(7), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["costs-snapshot", 7]);
    });
  });
});
