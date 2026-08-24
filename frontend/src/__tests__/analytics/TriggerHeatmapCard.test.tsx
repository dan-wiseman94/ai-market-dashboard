import { screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TriggerHeatmapCard } from "@/components/analytics/TriggerHeatmapCard";
import * as analytics from "@/hooks/useAnalytics";
import { renderWithProviders } from "../testUtils";

function mockHook(overrides: Partial<{ data: unknown; isLoading: boolean; error: Error | null }> = {}) {
  vi.spyOn(analytics, "useTriggerHeatmap").mockReturnValue({
    data: {
      cells: Array.from({ length: 168 }, (_, i) => ({
        weekday: Math.floor(i / 24),
        hour: i % 24,
        count: i === 50 ? 7 : 0,
      })),
    },
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof analytics.useTriggerHeatmap>);
}

describe("TriggerHeatmapCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders 168 cells + highlights the hottest one", () => {
    mockHook();
    const { container } = renderWithProviders(<TriggerHeatmapCard />);
    const cells = container.querySelectorAll("[data-testid=heat-cell]");
    expect(cells.length).toBe(168);
    expect(screen.getByText(/7 fires/)).toBeInTheDocument();
  });

  it("renders skeleton rows while loading", () => {
    mockHook({ data: undefined, isLoading: true });
    renderWithProviders(<TriggerHeatmapCard />);
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });
});
