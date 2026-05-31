import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AISecondOpinion } from "@/components/AISecondOpinion";
import * as hooks from "@/hooks/usePredictions";

function mockView(data: unknown) {
  vi.spyOn(hooks, "useAIView").mockReturnValue({ data } as never);
}

describe("AISecondOpinion", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders nothing when the AI has no open view", () => {
    mockView({ ticker: "NVDA", has_view: false });
    const { container } = render(<AISecondOpinion ticker="NVDA" against="bullish" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the AI call and an agree verdict", () => {
    mockView({
      ticker: "NVDA",
      has_view: true,
      direction: "bullish",
      confidence: 0.7,
      horizon_days: 7,
      agreement: "agree",
    });
    render(<AISecondOpinion ticker="NVDA" against="bullish" />);
    expect(screen.getByTestId("ai-second-opinion")).toBeInTheDocument();
    expect(screen.getByText("bullish")).toBeInTheDocument();
    expect(screen.getByText(/agrees with your thesis/)).toBeInTheDocument();
  });

  it("shows divergence when the AI disagrees", () => {
    mockView({
      ticker: "NVDA",
      has_view: true,
      direction: "bearish",
      confidence: 0.6,
      horizon_days: 7,
      agreement: "diverge",
    });
    render(<AISecondOpinion ticker="NVDA" against="bullish" />);
    expect(screen.getByText(/diverges from your thesis/)).toBeInTheDocument();
  });
});
