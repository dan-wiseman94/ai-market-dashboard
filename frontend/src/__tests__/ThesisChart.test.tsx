import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createChart } from "lightweight-charts";
import ThesisChart from "../components/ThesisChart";
import { mockApi, renderWithProviders } from "./testUtils";

const OHLC_FIXTURE = {
  ticker: "SPY",
  timeframe: "1D",
  bars: [
    { ts: "2026-05-01T09:30:00Z", open: 540, high: 545, low: 538, close: 542, volume: 50000 },
    { ts: "2026-05-02T09:30:00Z", open: 542, high: 548, low: 541, close: 546, volume: 48000 },
  ],
};

function mockOhlc() {
  return mockApi({ "GET /api/market/ohlc/": OHLC_FIXTURE });
}

// Grab the series mock returned by the global lightweight-charts mock (see setup.ts).
// createChart is vi.fn() → its return value is the chart mock → .addCandlestickSeries()
// is vi.fn() → its return value is the series mock with createPriceLine.
function getSeriesMock() {
  const chartMock = vi.mocked(createChart).mock.results.at(-1)?.value as {
    addCandlestickSeries: ReturnType<typeof vi.fn>;
  };
  return chartMock?.addCandlestickSeries.mock.results.at(-1)?.value as {
    createPriceLine: ReturnType<typeof vi.fn>;
  } | undefined;
}

beforeEach(() => {
  vi.mocked(createChart).mockClear();
});

describe("ThesisChart", () => {
  it("renders the chart container after data loads", async () => {
    mockOhlc();
    renderWithProviders(
      <ThesisChart ticker="SPY" entry="540.00" target="600.00" invalidation="520.00" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("thesis-chart")).toBeInTheDocument(),
    );
  });

  it("requests OHLC with the backend's lowercase '1d' timeframe (not '1D')", async () => {
    // The backend OHLC endpoint 400s on '1D' (only 1m/5m/15m/1h/1d are valid);
    // an uppercase timeframe here used to fail the thesis-detail page's chart
    // silently and trip the e2e console guard. Pin lowercase.
    const mock = mockOhlc();
    renderWithProviders(
      <ThesisChart ticker="SPY" entry="540" target="600" invalidation="520" />,
    );
    await waitFor(() => expect(screen.getByTestId("thesis-chart")).toBeInTheDocument());
    const ohlcCalls = mock.calls.filter((c) => c.url.includes("/api/market/ohlc/"));
    expect(ohlcCalls.length).toBeGreaterThan(0);
    for (const c of ohlcCalls) {
      expect(c.url).toContain("timeframe=1d");
      expect(c.url).not.toContain("timeframe=1D");
    }
  });

  it("shows a skeleton while OHLC data is loading", () => {
    // Never resolve the fetch — data stays loading
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderWithProviders(
      <ThesisChart ticker="SPY" entry="540" target="600" invalidation="520" />,
    );
    expect(screen.getByTestId("skeleton-thesis-chart")).toBeInTheDocument();
  });

  it("creates price lines with correct prices and titles for all three levels (string decimals)", async () => {
    mockOhlc();
    renderWithProviders(
      <ThesisChart ticker="SPY" entry="540.50" target="600.00" invalidation="520.25" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("thesis-chart")).toBeInTheDocument(),
    );

    const series = getSeriesMock();
    expect(series?.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({ price: 600, title: "Target" }),
    );
    expect(series?.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({ price: 520.25, title: "Invalidation" }),
    );
    expect(series?.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({ price: 540.5, title: "Entry" }),
    );
  });

  it("skips a price line when the level is null", async () => {
    mockOhlc();
    renderWithProviders(
      // No invalidation
      <ThesisChart ticker="SPY" entry="540.00" target="600.00" invalidation={null} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("thesis-chart")).toBeInTheDocument(),
    );

    const series = getSeriesMock();
    const calls = series?.createPriceLine.mock.calls ?? [];
    // Should have Target + Entry but NOT Invalidation
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Target")).toBe(true);
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Entry")).toBe(true);
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Invalidation")).toBe(false);
  });

  it("skips a price line when the level is undefined", async () => {
    mockOhlc();
    renderWithProviders(
      // No entry passed at all
      <ThesisChart ticker="SPY" target="600.00" invalidation="520.00" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("thesis-chart")).toBeInTheDocument(),
    );

    const series = getSeriesMock();
    const calls = series?.createPriceLine.mock.calls ?? [];
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Target")).toBe(true);
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Invalidation")).toBe(true);
    expect(calls.some((c: unknown[]) => (c[0] as { title: string }).title === "Entry")).toBe(false);
  });

  it("uses gain color for target and loss color for invalidation", async () => {
    mockOhlc();
    renderWithProviders(
      <ThesisChart ticker="SPY" target="600.00" invalidation="520.00" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("thesis-chart")).toBeInTheDocument(),
    );

    const series = getSeriesMock();
    const calls: Array<{ price: number; color: string; title: string }> =
      (series?.createPriceLine.mock.calls ?? []).map((c: unknown[]) => c[0] as { price: number; color: string; title: string });

    const targetLine = calls.find((c) => c.title === "Target");
    const invalidationLine = calls.find((c) => c.title === "Invalidation");
    // Gain color (green family)
    expect(targetLine?.color).toMatch(/#[0-9a-f]+/i);
    expect(targetLine?.color).toBe("#4fb38a");
    // Loss color (red family)
    expect(invalidationLine?.color).toBe("#c55c62");
  });

  it("renders nothing when fetch errors (no chart, no skeleton)", async () => {
    mockApi({ "GET /api/market/ohlc/": { status: 503, code: "error", message: "err" } });
    renderWithProviders(
      <ThesisChart ticker="SPY" entry="540" target="600" invalidation="520" />,
    );
    await waitFor(() =>
      expect(screen.queryByTestId("skeleton-thesis-chart")).not.toBeInTheDocument(),
    );
    // Chart container is also not rendered on error
    expect(screen.queryByTestId("thesis-chart")).not.toBeInTheDocument();
  });
});
