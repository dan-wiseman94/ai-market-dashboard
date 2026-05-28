import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProviderLeaderboardCard } from "@/components/analytics/ProviderLeaderboardCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useLeaderboard: () => ({
    data: {
      rows: [
        {
          provider: "claude", model: "claude-opus-4-8", runs: 40,
          total_cost_usd: "4.20", avg_latency_ms: 1800,
          avg_forward_return_pct: 1.23, coverage_pct: 60.0,
        },
        {
          provider: "openai", model: "gpt-5", runs: 15,
          total_cost_usd: "0.75", avg_latency_ms: 900,
          avg_forward_return_pct: null, coverage_pct: 0.0,
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ProviderLeaderboardCard", () => {
  it("renders one row per (provider,model)", () => {
    wrap(<ProviderLeaderboardCard />);
    expect(screen.getByText("claude-opus-4-8")).toBeInTheDocument();
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
  });

  it("shows — when forward-return is null", () => {
    wrap(<ProviderLeaderboardCard />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });
});
