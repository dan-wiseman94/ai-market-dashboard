import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mockApi, renderWithProviders } from "./testUtils";
import MirrorPage from "../pages/MirrorPage";

const FAKE = {
  horizon_days: 30,
  decision_outcomes: {
    status: "ok",
    buckets: [{ decision: "passed", n: 9, correct: 7, hit_rate: 0.78 }],
  },
  conviction_reliability: {
    status: "ok",
    verdict: "inverted",
    buckets: [
      { conviction: 5, n: 6, correct: 2, hit_rate: 0.33 },
      { conviction: 1, n: 6, correct: 4, hit_rate: 0.67 },
    ],
  },
};

function renderWith(payload: unknown) {
  mockApi({ "GET /api/analytics/trader-calibration/": payload });
  renderWithProviders(<MirrorPage />);
}

describe("MirrorPage", () => {
  it("renders decision outcomes and an inverted conviction verdict", async () => {
    renderWith(FAKE);
    await waitFor(() => expect(screen.getByText("Passed")).toBeInTheDocument());
    expect(screen.getByText(/passing on winners/i)).toBeInTheDocument();
    expect(screen.getByText(/Inverted/i)).toBeInTheDocument();
  });

  it("derives horizon buttons from the payload's horizons field", async () => {
    renderWith({ ...FAKE, horizons: [5, 30, 60] });
    // 3s: the default 1s waitFor window flakes when the full suite saturates the runner.
    await waitFor(
      () => expect(screen.getByRole("button", { name: "5d" })).toBeInTheDocument(),
      { timeout: 3000 },
    );
    expect(screen.getByRole("button", { name: "60d" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "7d" })).not.toBeInTheDocument();
  });

  it("shows an empty state when there is not enough history", async () => {
    renderWith({
      horizon_days: 30,
      decision_outcomes: { status: "insufficient_history", buckets: [] },
      conviction_reliability: { status: "insufficient_history", buckets: [], verdict: null },
    });
    await waitFor(() =>
      expect(screen.getAllByText(/Not enough history yet/i).length).toBeGreaterThan(0),
    );
  });
});
