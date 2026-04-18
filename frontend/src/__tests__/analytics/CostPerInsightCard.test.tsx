import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CostPerInsightCard } from "@/components/analytics/CostPerInsightCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useCostPerInsight: () => ({
    data: {
      total_cost_usd: "12.50", threads_with_ai: 20, snapshots_with_ai: 8,
      trigger_fires: 5, insights: 33, cost_per_insight_usd: "0.3788",
    },
    isLoading: false, error: null,
  }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("CostPerInsightCard", () => {
  it("shows total cost, insight count, and CPI", () => {
    wrap(<CostPerInsightCard />);
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.getByText(/33/)).toBeInTheDocument();
    expect(screen.getByText(/0\.3788/)).toBeInTheDocument();
  });
});
