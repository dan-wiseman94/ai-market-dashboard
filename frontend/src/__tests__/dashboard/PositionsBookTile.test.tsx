import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { PositionsBookTile } from "@/components/dashboard/PositionsBookTile";
import { mockApi, renderWithProviders } from "../testUtils";
import type { PortfolioPosition } from "@/api/portfolio";

const LONG_POSITION: PortfolioPosition = {
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

const SHORT_POSITION: PortfolioPosition = {
  id: 2,
  ticker: "TSLA",
  direction: "short",
  quantity: "5.00000000",
  avg_cost: "200.00",
  opened_at: "2026-05-02T00:00:00Z",
  closed_at: null,
  close_price: null,
  realized_pnl: null,
  status: "open",
  note: "",
  thesis_id: null,
  profile_id: null,
  unrealized: {
    last: 180.0,
    market_value: 900.0,
    unrealized_pnl: 100.0,
    unrealized_pct: 10.0,
  },
  created_at: "2026-05-02T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

const LOSS_POSITION: PortfolioPosition = {
  ...LONG_POSITION,
  id: 3,
  ticker: "NVDA",
  unrealized: {
    last: 130.0,
    market_value: 1300.0,
    unrealized_pnl: -200.0,
    unrealized_pct: -13.33,
  },
};

describe("PositionsBookTile", () => {
  it("renders EmptyState when there are no open positions", async () => {
    mockApi({ "GET /api/portfolio/positions/": [] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByText(/No open positions/i)).toBeInTheDocument(),
    );
  });

  it("renders ticker and direction for each position", async () => {
    mockApi({ "GET /api/portfolio/positions/": [LONG_POSITION, SHORT_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByText("AAPL")).toBeInTheDocument(),
    );
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByText("long")).toBeInTheDocument();
    expect(screen.getByText("short")).toBeInTheDocument();
  });

  it("renders per-position unrealized P&L with correct values", async () => {
    mockApi({ "GET /api/portfolio/positions/": [LONG_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByTestId("tile-pnl-1")).toBeInTheDocument(),
    );
    // Gain: +150.00
    expect(screen.getByTestId("tile-pnl-1")).toHaveTextContent("+150.00");
  });

  it("applies gain color class for positive P&L", async () => {
    mockApi({ "GET /api/portfolio/positions/": [LONG_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByTestId("tile-pnl-1")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tile-pnl-1").className).toContain("text-gain-400");
  });

  it("applies loss color class for negative P&L", async () => {
    mockApi({ "GET /api/portfolio/positions/": [LOSS_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByTestId("tile-pnl-3")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tile-pnl-3")).toHaveTextContent("-200.00");
    expect(screen.getByTestId("tile-pnl-3").className).toContain("text-loss-400");
  });

  it("renders summed total P&L in the tile header", async () => {
    // LONG +150, SHORT +100 → total +250
    mockApi({ "GET /api/portfolio/positions/": [LONG_POSITION, SHORT_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByTestId("tile-total-pnl")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tile-total-pnl")).toHaveTextContent("+250.00");
    expect(screen.getByTestId("tile-total-pnl").className).toContain("text-gain-400");
  });

  it("renders total P&L in loss color when negative", async () => {
    mockApi({ "GET /api/portfolio/positions/": [LOSS_POSITION] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() =>
      expect(screen.getByTestId("tile-total-pnl")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tile-total-pnl")).toHaveTextContent("-200.00");
    expect(screen.getByTestId("tile-total-pnl").className).toContain("text-loss-400");
  });

  it("requests the ?status=open filter", async () => {
    const { calls } = mockApi({ "GET /api/portfolio/positions/": [] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() => {
      const call = calls.find((c) => c.url.includes("status=open"));
      expect(call).toBeDefined();
    });
  });

  it("links to /portfolio", async () => {
    mockApi({ "GET /api/portfolio/positions/": [] });
    renderWithProviders(<PositionsBookTile />);
    await waitFor(() => {
      const links = screen.getAllByRole("link");
      expect(links.some((l) => l.getAttribute("href") === "/portfolio")).toBe(true);
    });
  });
});
