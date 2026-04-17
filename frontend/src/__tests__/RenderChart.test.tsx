import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RenderChart from "../pages/RenderChart";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

global.fetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [{ ts: "2026-04-17T09:30:00Z", open: 1, high: 2, low: 1, close: 2, volume: 0 }] }) }),
) as never;

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("RenderChart", () => {
  it("sets data-render-ready on body once chart finishes painting", async () => {
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/render/chart?ticker=SPY&timeframe=5m&bars=10"]}>
          <Routes><Route path="/render/chart" element={<RenderChart />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(document.body.dataset.renderReady).toBe("true"));
  });
});
