import { waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Chart from "../components/Chart";
import { mockFetch, renderWithProviders } from "./testUtils";

beforeEach(() => {
  mockFetch(() => ({
    ok: true,
    json: () =>
      Promise.resolve({
        ticker: "SPY",
        timeframe: "5m",
        bars: [
          { ts: "2026-04-17T09:30:00Z", open: 520, high: 522, low: 519, close: 521, volume: 1000 },
        ],
      }),
  }));
});

describe("Chart", () => {
  it("invokes onReady once data finishes loading", async () => {
    const onReady = vi.fn();
    renderWithProviders(<Chart ticker="SPY" timeframe="5m" bars={60} onReady={onReady} />);
    await waitFor(() => expect(onReady).toHaveBeenCalled());
  });
});
