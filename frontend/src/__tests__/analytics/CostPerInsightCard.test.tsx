import { screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CostPerInsightCard } from "@/components/analytics/CostPerInsightCard";
import * as analytics from "@/hooks/useAnalytics";
import { renderWithProviders } from "../testUtils";

function mockHook(overrides: Partial<{ data: unknown; isLoading: boolean; error: Error | null }> = {}) {
  vi.spyOn(analytics, "useCostPerInsight").mockReturnValue({
    data: {
      total_cost_usd: "12.50", threads_with_ai: 20, snapshots_with_ai: 8,
      trigger_fires: 5, insights: 33, cost_per_insight_usd: "0.3788",
    },
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof analytics.useCostPerInsight>);
}

describe("CostPerInsightCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows total cost, insight count, and CPI", () => {
    mockHook();
    renderWithProviders(<CostPerInsightCard />);
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.getByText(/33/)).toBeInTheDocument();
    expect(screen.getByText(/0\.3788/)).toBeInTheDocument();
  });

  it("renders skeleton rows while loading", () => {
    mockHook({ data: undefined, isLoading: true });
    renderWithProviders(<CostPerInsightCard />);
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });
});
