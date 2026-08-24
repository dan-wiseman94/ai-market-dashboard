import { screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { UnusualOptionsCard } from "@/components/analytics/UnusualOptionsCard";
import * as analytics from "@/hooks/useAnalytics";
import { renderWithProviders } from "../testUtils";

const ROW = {
  strike: "150", side: "call", expiry: "2026-05-15",
  volume: 20000, oi: 10000, iv: 0.55,
  volume_ratio: 2.0, iv_z: 1.8,
  triggers: ["iv_spike"], score: 3.8,
};

function mockHook(overrides: Partial<{ data: unknown; isLoading: boolean; error: Error | null }> = {}) {
  vi.spyOn(analytics, "useUnusualOptions").mockImplementation(
    (ticker: string) =>
      ({
        data: ticker ? { rows: [ROW] } : undefined,
        isLoading: false,
        error: null,
        ...overrides,
      }) as ReturnType<typeof analytics.useUnusualOptions>,
  );
}

describe("UnusualOptionsCard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders a placeholder before a ticker is entered", () => {
    mockHook();
    renderWithProviders(<UnusualOptionsCard />);
    expect(screen.getByText(/enter a ticker/i)).toBeInTheDocument();
  });

  it("renders unusual lines after input", () => {
    mockHook();
    renderWithProviders(<UnusualOptionsCard />);
    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "AAPL" },
    });
    expect(screen.getByText(/iv_spike/)).toBeInTheDocument();
    expect(screen.getByText(/2026-05-15/)).toBeInTheDocument();
  });

  it("keeps the ticker input visible and shows skeleton rows while loading", () => {
    mockHook({ data: undefined, isLoading: true });
    renderWithProviders(<UnusualOptionsCard />);
    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "AAPL" },
    });
    expect(screen.getByPlaceholderText(/ticker/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });
});
