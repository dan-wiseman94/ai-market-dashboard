import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OpenThesesTile } from "@/components/dashboard/OpenThesesTile";
import { renderWithProviders } from "../testUtils";
import type { DashboardThesis } from "@/hooks/useDashboard";

const bullish: DashboardThesis = {
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
};

const bearish: DashboardThesis = {
  id: 2,
  ticker: "TSLA",
  direction: "bearish",
  conviction: 3,
  entry: 250.0,
  target: 180.0,
  invalidation: 270.0,
  current: 220.0,
  pct_to_target: -18.18,
  pct_to_invalidation: 22.73,
};

describe("OpenThesesTile", () => {
  it("renders ticker + conviction + pct_to_target for each thesis", () => {
    renderWithProviders(<OpenThesesTile theses={[bullish, bearish]} />);

    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();

    // Conviction badges
    expect(screen.getByText("c4")).toBeInTheDocument();
    expect(screen.getByText("c3")).toBeInTheDocument();

    // Pct to target for bullish (positive)
    expect(screen.getByText("+8.1%")).toBeInTheDocument();
    // Pct to target for bearish (negative)
    expect(screen.getByText("-18.2%")).toBeInTheDocument();
  });

  it("shows direction badges for both theses", () => {
    renderWithProviders(<OpenThesesTile theses={[bullish, bearish]} />);
    expect(screen.getByText("bullish")).toBeInTheDocument();
    expect(screen.getByText("bearish")).toBeInTheDocument();
  });

  it("shows EmptyState when theses array is empty", () => {
    renderWithProviders(<OpenThesesTile theses={[]} />);
    expect(screen.getByText(/No open theses/i)).toBeInTheDocument();
  });

  it("each thesis links to /theses", () => {
    renderWithProviders(<OpenThesesTile theses={[bullish]} />);
    const links = screen.getAllByRole("link", { name: /AAPL/i });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", "/theses");
  });
});
