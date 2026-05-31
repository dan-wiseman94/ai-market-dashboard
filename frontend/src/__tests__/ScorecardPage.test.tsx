import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ScorecardPage from "@/pages/ScorecardPage";
import * as hooks from "@/hooks/useAnalytics";

function mock(data: unknown, isLoading = false) {
  vi.spyOn(hooks, "useCalibration").mockReturnValue({ data, isLoading } as never);
}

function mockDrill(data: unknown = undefined, isLoading = false) {
  vi.spyOn(hooks, "useCalibrationDrilldown").mockReturnValue({ data, isLoading } as never);
}

const POPULATED = {
  horizon: 30,
  scored: 2,
  attributable: 1,
  provider: [
    { provider: "claude", model: "claude-opus-4-8", n: 1, correct: 1, incorrect: 0, hit_rate: 1 },
  ],
  thesis: {
    brier: 0.12,
    prob_map: {},
    overall: {
      scored: 2,
      hit_rate: 0.5,
      correct: 1,
      incorrect: 1,
      mixed: 0,
      inconclusive: 0,
      avg_forward_return_pct: 3,
    },
    by_direction: {},
    buckets: [
      { conviction: 5, n: 2, correct: 1, incorrect: 1, mixed: 0, inconclusive: 0, hit_rate: 0.5 },
    ],
  },
};

describe("ScorecardPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state when nothing scored", () => {
    mock({
      horizon: 30,
      scored: 0,
      attributable: 0,
      provider: [],
      thesis: {
        buckets: [],
        brier: null,
        prob_map: {},
        overall: {
          scored: 0,
          hit_rate: null,
          correct: 0,
          incorrect: 0,
          mixed: 0,
          inconclusive: 0,
          avg_forward_return_pct: null,
        },
        by_direction: {},
      },
    });
    mockDrill();
    render(<ScorecardPage />);
    expect(screen.getByText(/No scored theses yet/i)).toBeInTheDocument();
  });

  it("renders buckets + provider rows when populated", () => {
    mock(POPULATED);
    mockDrill();
    render(<ScorecardPage />);
    expect(screen.getByText(/Thesis calibration/i)).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();
  });

  it("reveals the drill-down theses when a conviction is clicked", () => {
    mock(POPULATED);
    mockDrill({
      start: "x",
      end: "y",
      horizon: 30,
      count: 1,
      filters: { conviction: 5, direction: null, verdict: null },
      rows: [
        {
          thesis_id: 42,
          title: "AI capex",
          ticker: "NVDA",
          direction: "bullish",
          conviction: 5,
          verdict: "correct",
          forward_return_pct: 8.3,
          horizon_days: 30,
          completed_at: "2026-05-01T00:00:00Z",
          thread_id: null,
        },
      ],
    });
    render(
      <MemoryRouter>
        <ScorecardPage />
      </MemoryRouter>,
    );
    // The conviction "5" cell is a button (n > 0). Clicking it drills down.
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    const link = screen.getByRole("link", { name: /NVDA · AI capex/ });
    expect(link).toHaveAttribute("href", "/theses/42");
    expect(screen.getByText("correct")).toBeInTheDocument();
  });
});
