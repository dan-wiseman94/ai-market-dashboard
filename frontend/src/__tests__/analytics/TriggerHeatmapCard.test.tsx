import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TriggerHeatmapCard } from "@/components/analytics/TriggerHeatmapCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useTriggerHeatmap: () => ({
    data: {
      cells: Array.from({ length: 168 }, (_, i) => ({
        weekday: Math.floor(i / 24),
        hour: i % 24,
        count: i === 50 ? 7 : 0,
      })),
    },
    isLoading: false, error: null,
  }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("TriggerHeatmapCard", () => {
  it("renders 168 cells + highlights the hottest one", () => {
    const { container } = wrap(<TriggerHeatmapCard />);
    const cells = container.querySelectorAll("[data-testid=heat-cell]");
    expect(cells.length).toBe(168);
    expect(screen.getByText(/7 fires/)).toBeInTheDocument();
  });
});
