import { screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ObserverTimelineCard } from "@/components/analytics/ObserverTimelineCard";
import * as analytics from "@/hooks/useAnalytics";
import { renderWithProviders } from "../testUtils";

function mockHook(overrides: Partial<{ data: unknown; isLoading: boolean; error: Error | null }> = {}) {
  vi.spyOn(analytics, "useObserverTimeline").mockReturnValue({
    data: {
      days: [
        { date: "2026-04-01", success: 5, failed: 1, skipped: 0 },
        { date: "2026-04-02", success: 0, failed: 0, skipped: 3 },
      ],
    },
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof analytics.useObserverTimeline>);
}

describe("ObserverTimelineCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders one stack per day", () => {
    mockHook();
    renderWithProviders(<ObserverTimelineCard />);
    expect(screen.getByText("2026-04-01")).toBeInTheDocument();
    expect(screen.getByText("2026-04-02")).toBeInTheDocument();
  });

  it("renders skeleton rows while loading", () => {
    mockHook({ data: undefined, isLoading: true });
    renderWithProviders(<ObserverTimelineCard />);
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });
});
