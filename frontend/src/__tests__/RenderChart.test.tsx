import { waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import RenderChart from "../pages/RenderChart";
import { mockFetch, renderWithProviders } from "./testUtils";

beforeEach(() => {
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
});
