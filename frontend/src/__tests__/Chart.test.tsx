import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Chart from "../components/Chart";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [
        { ts: "2026-04-17T09:30:00Z", open: 520, high: 522, low: 519, close: 521, volume: 1000 },
      ]}),
    }),
  ) as never;
});

describe("Chart", () => {
  it("renders without crashing and calls onReady once data loads", async () => {
    const onReady = vi.fn();
    render(<Chart ticker="SPY" timeframe="5m" bars={60} onReady={onReady} />, { wrapper });
    await waitFor(() => expect(onReady).toHaveBeenCalled());
  });
});
