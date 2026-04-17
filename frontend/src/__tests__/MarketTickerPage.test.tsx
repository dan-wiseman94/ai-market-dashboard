import { describe, it, expect, vi } from "vitest";
import { render, waitFor, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MarketTickerPage from "../pages/MarketTickerPage";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

global.fetch = vi.fn((url: string) => {
  if (url.includes("/api/market/chain/")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({
      underlying_last: "100.00", expiries: { "2026-04-25": { calls: [], puts: [] } },
    })});
  }
  if (url.includes("/api/market/news/")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [] }) });
}) as never;

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("MarketTickerPage", () => {
  it("renders chart, chain, and news for given ticker", async () => {
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/market/SPY"]}>
          <Routes>
            <Route path="/market/:ticker" element={<MarketTickerPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText(/SPY/)).toBeInTheDocument();
    });
  });
});
