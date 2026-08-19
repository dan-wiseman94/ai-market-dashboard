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

function mockEval(data: unknown = undefined, isLoading = false) {
  vi.spyOn(hooks, "useLatestEvalRun").mockReturnValue({ data, isLoading } as never);
}

function mockAICal(data: unknown = undefined, isLoading = false) {
  vi.spyOn(hooks, "useAICalibration").mockReturnValue({ data, isLoading } as never);
}

function mockDrift(data: unknown = undefined, isLoading = false) {
  vi.spyOn(hooks, "useCalibrationDrift").mockReturnValue({ data, isLoading } as never);
}

function mockContra(data: unknown = undefined, isLoading = false) {
  vi.spyOn(hooks, "useContradictions").mockReturnValue({ data, isLoading } as never);
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

const EVAL_RUN = {
  id: 1,
  created_at: "2026-05-01T00:00:00Z",
  source: "scheduled",
  label: "scheduled",
  model: "claude-sonnet-4-6",
  horizon: 30,
  n: 12,
  skipped: 0,
  scored: 10,
  hit_rate: 0.6,
  brier: 0.21,
  avg_confidence: 0.75,
  calibration_error: 0.15,
  calibration: [
    { bin_low: 0.7, bin_high: 0.9, n: 8, hits: 5, observed_hit_rate: 0.625, mean_confidence: 0.8 },
  ],
};

const AI_CAL = {
  start: "x",
  end: "y",
  horizon: 30,
  overall: { scored: 5, hit_rate: 0.6, correct: 3, incorrect: 2, mixed: 0 },
  brier: 0.18,
  reliability: [
    {
      band: "0.7-0.8",
      n: 5,
      correct: 3,
      incorrect: 2,
      mean_confidence: 0.75,
      observed_hit_rate: 0.6,
    },
  ],
  by_provider_model: [
    { provider: "openai", model: "gpt-5", n: 5, correct: 3, incorrect: 2, hit_rate: 0.6 },
  ],
  by_direction: {},
  beat_the_straddle: { n: 5, beyond_priced: 2, within_priced: 3, beyond_rate: 0.4, edge_rate: 0.2 },
};

describe("ScorecardPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockAICal(); // default: no resolved AI predictions; the AI-calibration test overrides
    mockDrift(); // default: no drift data; the drift test overrides
    mockContra(); // default: no contradictions; the contradiction test overrides
  });

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
    mockEval();
    render(<ScorecardPage />);
    expect(screen.getByText(/No scored theses yet/i)).toBeInTheDocument();
  });

  it("renders buckets + provider rows when populated (no eval card without data)", () => {
    mock(POPULATED);
    mockDrill();
    mockEval();
    render(<ScorecardPage />);
    expect(screen.getByText(/Thesis calibration/i)).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.queryByText(/Model eval calibration/i)).not.toBeInTheDocument();
  });

  it("reveals the drill-down theses when a conviction is clicked", () => {
    mock(POPULATED);
    mockEval();
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

  it("renders the model eval-calibration card when an eval run exists", () => {
    mock(POPULATED);
    mockDrill();
    mockEval(EVAL_RUN);
    render(<ScorecardPage />);
    expect(screen.getByText(/Model eval calibration/i)).toBeInTheDocument();
    expect(screen.getByText(/claude-sonnet-4-6/)).toBeInTheDocument();
    expect(screen.getByText(/avg confidence 75%/)).toBeInTheDocument();
  });

  it("renders live AI prediction calibration when the AI has resolved calls", () => {
    mock(POPULATED);
    mockDrill();
    mockEval();
    mockAICal(AI_CAL);
    render(<ScorecardPage />);
    expect(screen.getByText(/Live AI prediction calibration/i)).toBeInTheDocument();
    expect(screen.getByText("0.7-0.8")).toBeInTheDocument();
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
    // #13 beat-the-straddle: actual move vs options-priced 1σ
    expect(screen.getByTestId("beat-the-straddle")).toHaveTextContent(/beyond the/i);
  });

  it("renders a calibration-drift warning for a drifting model", () => {
    mock(POPULATED);
    mockDrill();
    mockEval();
    mockDrift({
      generated_at: "z",
      window_days: 30,
      models: [
        { model: "opus", recent_error: 0.16, baseline_error: 0.05, delta: 0.11, drifting: true, direction: "overconfident", status: "scored", recent_runs: 3, baseline_runs: 3 },
        { model: "sonnet", recent_error: 0.05, baseline_error: 0.05, delta: 0.0, drifting: false, direction: "stable", status: "scored", recent_runs: 3, baseline_runs: 3 },
      ],
    });
    render(<ScorecardPage />);
    const drift = screen.getByTestId("calibration-drift");
    expect(drift).toHaveTextContent(/opus/);
    expect(drift).toHaveTextContent(/overconfident/);
    expect(drift).not.toHaveTextContent(/sonnet/);
  });

  it("renders open contradictions vs the house view", () => {
    mock(POPULATED);
    mockDrill();
    mockEval();
    mockContra({
      contradictions: [
        { ticker: "NVDA", prediction_direction: "bearish", stance: "bull", prediction_id: 1, predicted_at: "z" },
      ],
    });
    render(<ScorecardPage />);
    const c = screen.getByTestId("contradictions");
    expect(c).toHaveTextContent(/NVDA/);
    expect(c).toHaveTextContent(/bearish call vs bullish house view/i);
  });

  it("hides the live AI calibration section when no predictions resolved", () => {
    mock(POPULATED);
    mockDrill();
    mockEval();
    mockAICal();
    render(<ScorecardPage />);
    expect(screen.queryByText(/Live AI prediction calibration/i)).not.toBeInTheDocument();
  });
});
