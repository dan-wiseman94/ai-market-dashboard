import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ScorecardPage from "@/pages/ScorecardPage";
import * as hooks from "@/hooks/useAnalytics";

function mock(data: unknown, isLoading = false) {
  vi.spyOn(hooks, "useCalibration").mockReturnValue({ data, isLoading } as never);
}

describe("ScorecardPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state when nothing scored", () => {
    mock({ horizon: 30, scored: 0, attributable: 0, provider: [],
      thesis: { buckets: [], brier: null, prob_map: {},
        overall: { scored: 0, hit_rate: null, correct: 0, incorrect: 0, mixed: 0, inconclusive: 0, avg_forward_return_pct: null },
        by_direction: {} } });
    render(<ScorecardPage />);
    expect(screen.getByText(/No scored theses yet/i)).toBeInTheDocument();
  });

  it("renders buckets + provider rows when populated", () => {
    mock({ horizon: 30, scored: 2, attributable: 1,
      provider: [{ provider: "claude", model: "claude-opus-4-7", n: 1, correct: 1, incorrect: 0, hit_rate: 1 }],
      thesis: { brier: 0.12, prob_map: {},
        overall: { scored: 2, hit_rate: 0.5, correct: 1, incorrect: 1, mixed: 0, inconclusive: 0, avg_forward_return_pct: 3 },
        by_direction: {},
        buckets: [{ conviction: 5, n: 2, correct: 1, incorrect: 1, mixed: 0, inconclusive: 0, hit_rate: 0.5 }] } });
    render(<ScorecardPage />);
    expect(screen.getByText(/Thesis calibration/i)).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();
  });
});
