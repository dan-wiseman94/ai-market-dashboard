import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import PortfolioPage from "../pages/PortfolioPage";
import { mockApi, renderWithProviders } from "./testUtils";
import type { PortfolioPosition } from "@/api/portfolio";

const AAPL_POSITION: PortfolioPosition = {
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
  thesis_id: 7,
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

const TSLA_LOSS: PortfolioPosition = {
  id: 2,
  ticker: "TSLA",
  direction: "long",
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
    unrealized_pnl: -100.0,
    unrealized_pct: -10.0,
  },
  created_at: "2026-05-02T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

const CLOSED_AAPL: PortfolioPosition = {
  ...AAPL_POSITION,
  id: 3,
  status: "closed",
  close_price: "170.00",
  closed_at: "2026-05-20T00:00:00Z",
  realized_pnl: "200.00",
  unrealized: null,
};

describe("PortfolioPage", () => {
  it("shows skeleton while loading", () => {
    globalThis.fetch = (() => new Promise(() => {})) as typeof fetch;
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });

  it("shows EmptyState when no open positions", async () => {
    mockApi({ "GET /api/portfolio/positions/": [] });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    await waitFor(() =>
      expect(screen.getByText(/No open positions/i)).toBeInTheDocument(),
    );
  });

  it("renders ticker and direction for each open position", async () => {
    mockApi({ "GET /api/portfolio/positions/": [AAPL_POSITION, TSLA_LOSS] });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    await waitFor(() =>
      expect(screen.getByTestId("position-row-1")).toBeInTheDocument(),
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getAllByText("long").length).toBeGreaterThanOrEqual(2);
  });

  it("renders gain-colored P&L for profit and loss-colored for loss", async () => {
    mockApi({ "GET /api/portfolio/positions/": [AAPL_POSITION, TSLA_LOSS] });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    await waitFor(() =>
      expect(screen.getByTestId("pnl-1")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("pnl-1")).toHaveTextContent("+150.00");
    expect(screen.getByTestId("pnl-1").className).toContain("text-gain-400");

    expect(screen.getByTestId("pnl-2")).toHaveTextContent("-100.00");
    expect(screen.getByTestId("pnl-2").className).toContain("text-loss-400");
  });

  it("renders thesis link when thesis_id is set", async () => {
    mockApi({ "GET /api/portfolio/positions/": [AAPL_POSITION] });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    await waitFor(() =>
      expect(screen.getByText("Thesis #7")).toBeInTheDocument(),
    );
    const link = screen.getByText("Thesis #7").closest("a");
    expect(link).toHaveAttribute("href", "/theses/7");
  });

  it("add form calls createPosition with correct args", async () => {
    const { calls } = mockApi({
      "GET /api/portfolio/positions/": [],
      "POST /api/portfolio/positions/": AAPL_POSITION,
    });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });

    await waitFor(() =>
      expect(screen.getByTestId("add-position-btn")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("add-position-btn"));

    await waitFor(() =>
      expect(screen.getByTestId("add-position-form")).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByTestId("input-ticker"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("input-quantity"), { target: { value: "10" } });
    fireEvent.change(screen.getByTestId("input-avg-cost"), { target: { value: "150.00" } });
    fireEvent.submit(screen.getByTestId("add-position-form"));

    await waitFor(() => {
      const postCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/portfolio/positions/"));
      expect(postCall).toBeDefined();
      expect(postCall?.body).toMatchObject({
        ticker: "AAPL",
        direction: "long",
        quantity: "10",
        avg_cost: "150.00",
      });
    });
  });

  it("close button opens form; submitting calls closePosition", async () => {
    const { calls } = mockApi({
      "GET /api/portfolio/positions/": [AAPL_POSITION],
      "POST /api/portfolio/positions/1/close/": CLOSED_AAPL,
    });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });

    await waitFor(() =>
      expect(screen.getByTestId("open-close-btn-1")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("open-close-btn-1"));

    await waitFor(() =>
      expect(screen.getByTestId("close-price-input-1")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByTestId("close-price-input-1"), {
      target: { value: "170.00" },
    });
    fireEvent.submit(screen.getByTestId("close-form-1"));

    await waitFor(() => {
      const closeCall = calls.find(
        (c) => c.method === "POST" && c.url.includes("/api/portfolio/positions/1/close/"),
      );
      expect(closeCall).toBeDefined();
      expect(closeCall?.body).toMatchObject({ close_price: "170.00" });
    });
  });

  it("shows closed positions with realized P&L when toggled to closed view", async () => {
    const { calls } = mockApi({
      "GET /api/portfolio/positions/": [CLOSED_AAPL],
    });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });

    await waitFor(() =>
      expect(screen.getByTestId("view-closed-btn")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("view-closed-btn"));

    await waitFor(() => {
      const call = calls.find((c) => c.url.includes("status=closed"));
      expect(call).toBeDefined();
    });

    await waitFor(() =>
      expect(screen.getByTestId("position-row-3")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("realized-3")).toHaveTextContent("+200.00");
    expect(screen.getByTestId("realized-3").className).toContain("text-gain-400");
  });

  it("requests ?status=open when open view is selected", async () => {
    const { calls } = mockApi({ "GET /api/portfolio/positions/": [] });
    renderWithProviders(<PortfolioPage />, { initialEntries: ["/portfolio"] });
    await waitFor(() => {
      const call = calls.find((c) => c.url.includes("status=open"));
      expect(call).toBeDefined();
    });
  });
});
