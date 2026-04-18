import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ObserverTimelineCard } from "@/components/analytics/ObserverTimelineCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useObserverTimeline: () => ({
    data: {
      days: [
        { date: "2026-04-01", success: 5, failed: 1, skipped: 0 },
        { date: "2026-04-02", success: 0, failed: 0, skipped: 3 },
      ],
    },
    isLoading: false, error: null,
  }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ObserverTimelineCard", () => {
  it("renders one stack per day", () => {
    wrap(<ObserverTimelineCard />);
    expect(screen.getByText("2026-04-01")).toBeInTheDocument();
    expect(screen.getByText("2026-04-02")).toBeInTheDocument();
  });
});
