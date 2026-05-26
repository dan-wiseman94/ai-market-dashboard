// frontend/src/__tests__/ProviderLeaderboardCard.label.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ProviderLeaderboardCard } from "@/components/analytics/ProviderLeaderboardCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useLeaderboard: () => ({ data: { rows: [] }, isLoading: false, isError: false, error: null }),
}));

describe("ProviderLeaderboardCard", () => {
  it("explains the trading-day horizon + coverage", () => {
    render(<ProviderLeaderboardCard />);
    expect(screen.getByText(/trading session/i)).toBeInTheDocument();
    expect(screen.getByText(/coverage/i)).toBeInTheDocument();
  });
});
