import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import PredictionsPage from "@/pages/PredictionsPage";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";

const ROW = {
  id: 7,
  ticker: "NVDA",
  direction: "bullish",
  horizon_days: 7,
  confidence: 0.72,
  expected_move_pct: 3.1,
  rationale: "Breakout above the 20-day with breadth confirming.",
  invalidation_price: null,
  invalidation_note: "it closes back under 118",
  provider: "claude",
  model: "claude-opus-5",
  status: "resolved",
  predicted_at: "2026-06-01T14:00:00Z",
  resolve_at: "2026-06-08T14:00:00Z",
  resolved_at: "2026-06-08T14:00:00Z",
  invalidated_at: null,
  forward_return_pct: 2.5,
  verdict: "correct",
  source_message_id: 3,
  source_snapshot_id: 4,
  profile_id: 1,
  profile_name: "Swing",
  created_at: "2026-06-01T14:00:00Z",
  updated_at: "2026-06-08T14:00:00Z",
};

function counts(over: Record<string, number | null> = {}) {
  return {
    open: 2,
    resolving: 0,
    resolved: 3,
    invalidated: 1,
    correct: 2,
    incorrect: 1,
    mixed: 0,
    inconclusive: 0,
    total: 6,
    avg_forward_return_pct: 1.25,
    hit_rate: 0.6667,
    ...over,
  };
}

let mock: FetchMock | undefined;
afterEach(() => mock?.restore());

function render(
  statsOver: Record<string, number | null> = {},
  results: Array<Record<string, unknown>> = [ROW],
  byTicker: Array<Record<string, unknown>> = [{ ticker: "NVDA", ...counts() }],
) {
  mock = mockApi({
    "GET /api/predictions/stats/": {
      filters: { ticker: null, status: null, horizon: null },
      totals: counts(statsOver),
      by_ticker: byTicker,
    },
    "GET /api/predictions/": { count: results.length, next: null, previous: null, results },
  });
  renderWithProviders(<PredictionsPage />);
}

describe("PredictionsPage", () => {
  it("renders the stats header and a ledger row", async () => {
    render();
    const stats = within(await screen.findByTestId("prediction-stats"));
    expect(stats.getByText("67%")).toBeInTheDocument();
    expect(stats.getByText("+1.25%")).toBeInTheDocument();
    expect(stats.getByText("2/3 decisive")).toBeInTheDocument();
    expect(screen.getByText(/Breakout above the 20-day/)).toBeInTheDocument();
    expect(screen.getByTestId("prediction-row-7")).toBeInTheDocument();
  });

  it("renders a null hit rate as 'no decisive calls', never 0%", async () => {
    // A null hit rate means nothing decisive has resolved. Showing 0% would claim
    // every scored call was wrong — the opposite of an honest 'unknown'.
    render({ hit_rate: null, avg_forward_return_pct: null, correct: 0, incorrect: 0 });
    expect(await screen.findByText(/No decisive calls yet/i)).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing has resolved yet/i)).toBeInTheDocument();
  });

  it("renders a null per-ticker hit rate as an em dash", async () => {
    render({}, [ROW], [{ ticker: "SPY", ...counts({ hit_rate: null, avg_forward_return_pct: null }) }]);
    const row = await screen.findByTestId("ticker-row-SPY");
    expect(within(row).getAllByText("—").length).toBe(2);
  });

  it("sends the ticker filter to both the ledger and the stats endpoint", async () => {
    render();
    await screen.findByTestId("prediction-row-7");
    await userEvent.type(screen.getByLabelText(/ticker/i), "spy");
    await waitFor(() => {
      const urls = (mock?.calls ?? []).map((c) => c.url);
      expect(urls.some((u) => u.startsWith("/api/predictions/?ticker=spy"))).toBe(true);
      expect(urls.some((u) => u.includes("/stats/?ticker=spy"))).toBe(true);
    });
  });

  it("filters by status", async () => {
    render();
    await screen.findByTestId("prediction-row-7");
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "open");
    await waitFor(() =>
      expect((mock?.calls ?? []).some((c) => c.url.includes("status=open"))).toBe(true),
    );
  });

  it("shows an empty state when nothing matches", async () => {
    render({}, []);
    expect(await screen.findByText(/No predictions match/i)).toBeInTheDocument();
  });

  it("disables both pagination controls on a single page", async () => {
    render();
    await screen.findByTestId("prediction-row-7");
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });
});
