import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ObservationReportCard, { type ObservationReport } from "../components/ObservationReportCard";

// Mock html2canvas so SaveCardButton renders without a real canvas
vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({ toDataURL: () => "data:image/png;base64,x" })),
}));

const report: ObservationReport = {
  headline: "SPY grinds toward 525",
  bias: "neutral",
  summary: "Price respects rising 20-EMA.",
  signals: [
    { ticker: "SPY", bias: "bullish", thesis: "base pattern", invalidation: "below 520", confidence: 0.7 },
  ],
  key_levels: [{ label: "prior day high", price: 524.5, kind: "resistance" }],
  risks: ["CPI tomorrow"],
  next_check_in: "after 10:00 breadth",
};

describe("ObservationReportCard", () => {
  it("renders headline, summary, signals, levels, risks", () => {
    render(<ObservationReportCard report={report} />);
    expect(screen.getByText("SPY grinds toward 525")).toBeInTheDocument();
    expect(screen.getByText(/Price respects/)).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/prior day high/)).toBeInTheDocument();
    expect(screen.getByText(/CPI tomorrow/)).toBeInTheDocument();
    expect(screen.getByText(/after 10:00 breadth/)).toBeInTheDocument();
  });

  it("colors bias class for neutral", () => {
    render(<ObservationReportCard report={report} />);
    const badge = screen.getAllByText(/neutral/i)[0];
    expect(badge.className).toContain("text-slate-300");
  });

  it("renders the directional call and its grounding when the AI made one", () => {
    render(
      <ObservationReportCard
        report={{
          ...report,
          predicted_direction: "bullish",
          predicted_horizon_days: 5,
          predicted_confidence: 0.72,
          grounding: ["quotes", "chain analytics"],
        }}
      />,
    );
    // This call is what becomes an AIPrediction, so it has to be visible here.
    expect(screen.getByTestId("observation-call").textContent).toBe("Call: bullish · 5d · 72%");
    expect(screen.getByText("chain analytics")).toBeInTheDocument();
  });

  it("omits the call line when the report carries no directional call", () => {
    render(<ObservationReportCard report={report} />);
    expect(screen.queryByTestId("observation-call")).not.toBeInTheDocument();
  });

  it("renders a SaveCardButton in the card header", () => {
    render(<ObservationReportCard report={report} />);
    expect(screen.getByRole("button", { name: /save image/i })).toBeInTheDocument();
  });
});
