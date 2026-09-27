import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePortfolioPositions, useClosePosition, useDeletePosition } from "@/hooks/usePortfolio";
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
