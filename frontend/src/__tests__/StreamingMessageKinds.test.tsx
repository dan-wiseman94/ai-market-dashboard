import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import StreamingMessage from "@/components/StreamingMessage";
import type { ConsensusReport, PostMortemReportContent } from "@/api/observation";

vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({ toDataURL: () => "data:image/png;base64,x" })),
}));

const CONSENSUS: ConsensusReport = {
  n_providers: 2,
  bias_agreement: 1,
  modal_bias: "bearish",
  divergent: false,
  per_ticker: {},
  note: "",
  takes: [
    { provider: "claude", model: "claude-opus-5", bias: "bearish", signal_bias: {} },
    { provider: "openai", model: "gpt-5.6-sol", bias: "bearish", signal_bias: {} },
  ],
};

const POSTMORTEM: PostMortemReportContent = {
  summary: "Thesis played out.",
  what_worked: ["entry timing"],
  what_missed: [],
  lessons: ["size smaller"],
  would_repeat: true,
  ai: { provider: "openai", model: "gpt-5.6-sol" },
};

describe("StreamingMessage — every structured kind gets its own card", () => {
  it("renders a consensus report", () => {
    render(
      <StreamingMessage role="assistant" text="" status="done" kind="consensus_report"
        report={CONSENSUS} />,
    );
    expect(screen.getByText("2 of 2 agree (100%)")).toBeInTheDocument();
  });

  it("renders a post-mortem narrative with its provider", () => {
    render(
      <StreamingMessage role="assistant" text="" status="done" kind="postmortem_report"
        report={POSTMORTEM} />,
    );
    expect(screen.getByText("Thesis played out.")).toBeInTheDocument();
    expect(screen.getByText("entry timing")).toBeInTheDocument();
    expect(screen.getByText("size smaller")).toBeInTheDocument();
    expect(screen.getByText("would repeat")).toBeInTheDocument();
    expect(screen.getByTestId("ai-attribution").textContent).toBe("OpenAI · gpt-5.6-sol");
  });

  it("renders a war-room verdict", () => {
    render(
      <StreamingMessage role="assistant" text="" status="done" kind="warroom_verdict"
        verdict={{
          verdict: "bull case stronger",
          confidence: 0.7,
          strongest_bull: "breadth",
          strongest_bear: "rates",
          what_would_change_my_mind: "a close below 500",
          ai: { provider: "claude", model: "claude-opus-5" },
        }} />,
    );
    expect(screen.getByText("bull case stronger")).toBeInTheDocument();
    expect(screen.getByText("70% conf")).toBeInTheDocument();
    expect(screen.getByText(/a close below 500/)).toBeInTheDocument();
    expect(screen.getByTestId("ai-attribution").textContent).toBe("Claude · claude-opus-5");
  });

  it("marks a cached observation, a capability warning and an investigation", () => {
    const { rerender } = render(
      <StreamingMessage role="assistant" text="Reused" status="done" kind="cached_observation" />,
    );
    expect(screen.getByText("cached")).toBeInTheDocument();
    expect(screen.getByText("Reused")).toBeInTheDocument();

    rerender(
      <StreamingMessage role="assistant" text="OpenAI ignores thinking" status="done"
        kind="capability_warning" />,
    );
    expect(screen.getByText("warning")).toBeInTheDocument();

    rerender(<StreamingMessage role="assistant" text="looked around" status="done" kind="investigation" />);
    expect(screen.getByText("investigation")).toBeInTheDocument();
  });

  it("leaves an ordinary response unchipped", () => {
    render(<StreamingMessage role="assistant" text="Plain answer" status="done" />);
    expect(screen.getByText("Plain answer")).toBeInTheDocument();
    expect(screen.queryByText("cached")).not.toBeInTheDocument();
  });
});
