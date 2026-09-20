import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ConsensusReportCard, { agreementLine } from "@/components/ConsensusReportCard";
import type { ConsensusReport } from "@/api/observation";

// SaveCardButton rasterizes the card; jsdom has no canvas.
vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({ toDataURL: () => "data:image/png;base64,x" })),
}));

const REPORT: ConsensusReport = {
  n_providers: 3,
  bias_agreement: 0.6667,
  modal_bias: "bullish",
  divergent: true,
  per_ticker: {
    SPY: {
      agreement: 0.6667,
      modal: "bullish",
      takes: {
        "claude/claude-opus-5": "bullish",
        "openai/gpt-5.6-sol": "bullish",
        "local/llama3": "bearish",
      },
    },
  },
  takes: [
    { provider: "claude", model: "claude-opus-5", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "openai", model: "gpt-5.6-sol", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "local", model: "llama3", bias: "bearish", signal_bias: { SPY: "bearish" } },
  ],
  note: "",
};

const DEGRADED: ConsensusReport = {
  ...REPORT,
  n_providers: 1,
  bias_agreement: null,
  divergent: false,
  takes: [REPORT.takes[0]],
  per_ticker: {},
  note: "single provider — no consensus available",
};

describe("agreementLine", () => {
  it("counts the agreeing providers", () => {
    expect(agreementLine(REPORT)).toBe("2 of 3 agree (67%)");
  });

  it("is silent below two takes, where no consensus is meaningful", () => {
    expect(agreementLine(DEGRADED)).toBeNull();
  });
});

describe("ConsensusReportCard", () => {
  it("shows agreement, divergence, every take and the per-ticker split", () => {
    render(<ConsensusReportCard report={REPORT} />);
    expect(screen.getByText("2 of 3 agree (67%)")).toBeInTheDocument();
    expect(screen.getByText(/divergent — do more homework/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("ai-attribution")).toHaveLength(3);
    const row = screen.getByRole("row", { name: /SPY/ });
    expect(row).toBeInTheDocument();
    expect(row.textContent).toContain("67%");
  });

  it("states the single-provider case honestly rather than implying agreement", () => {
    render(<ConsensusReportCard report={DEGRADED} />);
    expect(screen.getByText(/single provider — no consensus available/)).toBeInTheDocument();
    expect(screen.queryByText(/agree \(/)).not.toBeInTheDocument();
    expect(screen.queryByText(/divergent/i)).not.toBeInTheDocument();
  });
});
