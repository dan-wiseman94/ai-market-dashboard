import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderWith(payload: unknown) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(payload) }),
  ) as never;
  render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter>
        <MirrorPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MirrorPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders decision outcomes and an inverted conviction verdict", async () => {
    renderWith(FAKE);
    await waitFor(() => expect(screen.getByText("Passed")).toBeInTheDocument());
    expect(screen.getByText(/passing on winners/i)).toBeInTheDocument();
    expect(screen.getByText(/Inverted/i)).toBeInTheDocument();
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
