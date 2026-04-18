import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UnusualOptionsCard } from "@/components/analytics/UnusualOptionsCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useUnusualOptions: (ticker: string) => ({
    data: ticker
      ? {
          rows: [{
            strike: "150", side: "call", expiry: "2026-05-15",
            volume: 20000, oi: 10000, iv: 0.55,
            volume_ratio: 2.0, iv_z: 1.8,
            triggers: ["iv_spike"], score: 3.8,
          }],
        }
      : undefined,
    isLoading: false, error: null,
  }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("UnusualOptionsCard", () => {
  it("renders a placeholder before a ticker is entered", () => {
    wrap(<UnusualOptionsCard />);
    expect(screen.getByText(/enter a ticker/i)).toBeInTheDocument();
  });

  it("renders unusual lines after input", () => {
    wrap(<UnusualOptionsCard />);
    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "AAPL" },
    });
    expect(screen.getByText(/iv_spike/)).toBeInTheDocument();
    expect(screen.getByText(/2026-05-15/)).toBeInTheDocument();
  });
});
