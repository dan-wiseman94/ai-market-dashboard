import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ObservationReportCard, { type ObservationReport } from "../components/ObservationReportCard";

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
});
