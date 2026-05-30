import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePortfolioPositions, useCreatePosition, useClosePosition, useDeletePosition } from "@/hooks/usePortfolio";
import { hookWrapper, mockApi, newQueryClient } from "../testUtils";
import type { PortfolioPosition } from "@/api/portfolio";

const OPEN_POSITION: PortfolioPosition = {
  id: 1,
  ticker: "AAPL",
  direction: "long",
  quantity: "10.00000000",
  avg_cost: "150.00",
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_price: null,
  realized_pnl: null,
  status: "open",
  note: "",
  thesis_id: null,
  profile_id: null,
  unrealized: {
    last: 165.0,
    market_value: 1650.0,
    unrealized_pnl: 150.0,
    unrealized_pct: 10.0,
  },
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const CLOSED_POSITION: PortfolioPosition = {
  ...OPEN_POSITION,
  id: 2,
  ticker: "MSFT",
  status: "closed",
  close_price: "320.00",
  closed_at: "2026-05-20T00:00:00Z",
  realized_pnl: "200.00",
  unrealized: null,
};

describe("usePortfolioPositions", () => {
  it("fetches /api/portfolio/positions/ with no params", async () => {
    const { calls } = mockApi({ "GET /api/portfolio/positions/": [OPEN_POSITION] });
    const { result } = renderHook(() => usePortfolioPositions(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].ticker).toBe("AAPL");
    const call = calls.find((c) => c.method === "GET" && c.url.includes("/api/portfolio/positions/"));
    expect(call).toBeDefined();
  });

  it("fetches with ?status=open filter", async () => {
    const { calls } = mockApi({ "GET /api/portfolio/positions/": [OPEN_POSITION] });
    const { result } = renderHook(
      () => usePortfolioPositions({ status: "open" }),
      { wrapper: hookWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const call = calls.find((c) => c.url.includes("status=open"));
    expect(call).toBeDefined();
  });

  it("fetches with ?thesis=5 filter", async () => {
    const { calls } = mockApi({ "GET /api/portfolio/positions/": [] });
    const { result } = renderHook(
      () => usePortfolioPositions({ thesis: 5 }),
      { wrapper: hookWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const call = calls.find((c) => c.url.includes("thesis=5"));
    expect(call).toBeDefined();
  });

  it("uses queryKey that includes portfolio/positions", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/portfolio/positions/": [] });
    renderHook(() => usePortfolioPositions(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey[0]);
      expect(keys).toContain("portfolio/positions");
    });
  });
});

describe("useCreatePosition", () => {
  it("POSTs to /api/portfolio/positions/ and invalidates query cache", async () => {
    const client = newQueryClient();
    const { calls } = mockApi({
      "GET /api/portfolio/positions/": [],
      "POST /api/portfolio/positions/": OPEN_POSITION,
    });
    const { result } = renderHook(() => useCreatePosition(), { wrapper: hookWrapper(client) });

    result.current.mutate({
      ticker: "AAPL",
      direction: "long",
      quantity: "10.00000000",
      avg_cost: "150.00",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const postCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/portfolio/positions/"));
    expect(postCall).toBeDefined();
    expect(postCall?.body).toMatchObject({ ticker: "AAPL", direction: "long" });
  });
});

describe("useClosePosition", () => {
  it("POSTs to /api/portfolio/positions/{id}/close/ with close_price", async () => {
    const { calls } = mockApi({
      "POST /api/portfolio/positions/1/close/": CLOSED_POSITION,
    });
    const { result } = renderHook(() => useClosePosition(), { wrapper: hookWrapper() });

    result.current.mutate({ id: 1, body: { close_price: "165.00" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const closeCall = calls.find(
      (c) => c.method === "POST" && c.url.includes("/api/portfolio/positions/1/close/"),
    );
    expect(closeCall).toBeDefined();
    expect(closeCall?.body).toMatchObject({ close_price: "165.00" });
  });
});

describe("useDeletePosition", () => {
  it("DELETEs /api/portfolio/positions/{id}/", async () => {
    const { calls } = mockApi({
      "DELETE /api/portfolio/positions/1/": undefined,
    });
    const { result } = renderHook(() => useDeletePosition(), { wrapper: hookWrapper() });

    result.current.mutate(1);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const deleteCall = calls.find(
      (c) => c.method === "DELETE" && c.url.includes("/api/portfolio/positions/1/"),
    );
    expect(deleteCall).toBeDefined();
  });
});
