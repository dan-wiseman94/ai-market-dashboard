import { screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProviderLeaderboardCard } from "@/components/analytics/ProviderLeaderboardCard";
import * as analytics from "@/hooks/useAnalytics";
import { renderWithProviders } from "../testUtils";

function mockHook(overrides: Partial<{ data: unknown; isLoading: boolean; error: Error | null }> = {}) {
  vi.spyOn(analytics, "useLeaderboard").mockReturnValue({
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
    ...overrides,
  } as ReturnType<typeof analytics.useLeaderboard>);
}

describe("ProviderLeaderboardCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders one row per (provider,model)", () => {
    mockHook();
    renderWithProviders(<ProviderLeaderboardCard />);
    expect(screen.getByText("claude-opus-4-8")).toBeInTheDocument();
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
  });

  it("shows — when forward-return is null", () => {
    mockHook();
    renderWithProviders(<ProviderLeaderboardCard />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("renders skeleton rows while loading", () => {
    mockHook({ data: undefined, isLoading: true });
    renderWithProviders(<ProviderLeaderboardCard />);
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });
});
