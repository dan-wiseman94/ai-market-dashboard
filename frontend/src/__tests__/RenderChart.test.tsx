import { waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import RenderChart from "../pages/RenderChart";
import { mockFetch, renderWithProviders } from "./testUtils";

beforeEach(() => {
  // data-render-ready lives on document.body and persists across jsdom tests;
  // clear it so each test only sees its own render flip the flag.
  document.body.removeAttribute("data-render-ready");
  mockFetch(() => ({
    ok: true,
    json: () =>
      Promise.resolve({
        ticker: "SPY",
        timeframe: "5m",
        bars: [{ ts: "2026-04-17T09:30:00Z", open: 1, high: 2, low: 1, close: 2, volume: 0 }],
      }),
  }));
});

describe("RenderChart", () => {
  it("flips data-render-ready on body once chart finishes painting", async () => {
    renderWithProviders(<RenderChart />, {
      initialEntries: ["/render/chart?ticker=SPY&timeframe=5m&bars=10"],
      routePath: "/render/chart",
    });
    await waitFor(() => expect(document.body.dataset.renderReady).toBe("true"));
  });

  it("flips data-render-ready even when OHLC returns no bars", async () => {
    // A successful-but-empty response (e.g. an index with no candles) must still
    // signal ready, otherwise the headless capture hangs until the 15s timeout.
    mockFetch(() => ({
      ok: true,
      json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [] }),
    }));
    renderWithProviders(<RenderChart />, {
      initialEntries: ["/render/chart?ticker=SPY&timeframe=5m&bars=10"],
      routePath: "/render/chart",
    });
    await waitFor(() => expect(document.body.dataset.renderReady).toBe("true"));
  });

  it("shows a no-data message when OHLC returns no bars", async () => {
    mockFetch(() => ({
      ok: true,
      json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [] }),
    }));
    const { findByText } = renderWithProviders(<RenderChart />, {
      initialEntries: ["/render/chart?ticker=SPY&timeframe=5m&bars=10"],
      routePath: "/render/chart",
    });
    expect(await findByText(/no .*data/i)).toBeTruthy();
  });
});
