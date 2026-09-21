import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import type { ConsensusReport } from "@/api/observation";
import ConsensusReportCard from "./ConsensusReportCard";

const divergent: ConsensusReport = {
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
        "local/llama-3.1-70b": "bearish",
      },
    },
    NVDA: {
      agreement: 1,
      modal: "bullish",
      takes: {
        "claude/claude-opus-5": "bullish",
        "openai/gpt-5.6-sol": "bullish",
      },
    },
  },
  takes: [
    { provider: "claude", model: "claude-opus-5", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "openai", model: "gpt-5.6-sol", bias: "bullish", signal_bias: { SPY: "bullish" } },
    { provider: "local", model: "llama-3.1-70b", bias: "bearish", signal_bias: { SPY: "bearish" } },
  ],
  note: "",
};

const meta = {
  title: "Observer/ConsensusReportCard",
  component: ConsensusReportCard,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Cross-provider agreement on one snapshot: the headline agreement fraction, a divergence flag, each provider's take, and where the providers split per ticker. Degrades to an explicit single-provider note rather than implying a consensus that was never reached.",
      },
    },
  },
  argTypes: {
    report: { control: "object", description: "The aggregated ConsensusReport payload." },
  },
} satisfies Meta<typeof ConsensusReportCard>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Three providers, two agreeing — the divergence flag earns its place. */
export const Divergent: Story = {
  args: { report: divergent },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("2 of 3 agree (67%)")).toBeVisible();
  },
};

/** Unanimous: same shape, no divergence pill. */
export const Unanimous: Story = {
  args: {
    report: {
      ...divergent,
      bias_agreement: 1,
      divergent: false,
      takes: divergent.takes.slice(0, 2),
      per_ticker: { SPY: { agreement: 1, modal: "bullish", takes: {
        "claude/claude-opus-5": "bullish",
        "openai/gpt-5.6-sol": "bullish",
      } } },
      n_providers: 2,
    },
  },
};

/** One usable provider — the honest degraded shape, not a fabricated consensus. */
export const SingleProvider: Story = {
  args: {
    report: {
      ...divergent,
      n_providers: 1,
      bias_agreement: null,
      divergent: false,
      takes: [divergent.takes[0]],
      per_ticker: {},
      note: "single provider — no consensus available",
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText(/single provider/)).toBeVisible();
  },
};
