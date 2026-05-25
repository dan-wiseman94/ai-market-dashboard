import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import ObservationReportCard, { type ObservationReport } from "./ObservationReportCard";

const meta = {
  title: "Observer/ObservationReportCard",
  component: ObservationReportCard,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Typed structured-observation card: bias chip, summary, signals, key levels, and risks. Sections hide when empty.",
      },
    },
  },
  argTypes: {
    report: { control: "object", description: "The structured ObservationReport payload." },
  },
} satisfies Meta<typeof ObservationReportCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const bullish: ObservationReport = {
  headline: "S&P coiling under resistance",
  bias: "bullish",
  summary: "Breadth firming while price consolidates beneath the range high.",
  signals: [
    {
      ticker: "SPY",
      bias: "bullish",
      thesis: "Higher lows pressing into a flat top.",
      invalidation: "Daily close below 520.",
      confidence: 0.72,
    },
  ],
  key_levels: [
    { label: "Range high", price: 530.5, kind: "resistance" },
    { label: "Breakout pivot", price: 521.0, kind: "pivot" },
  ],
  risks: ["CPI print Thursday could whipsaw the setup."],
  next_check_in: "after the cash open",
};

/** A full structured observation: bias chip, signals, key levels, risks. */
export const Bullish: Story = {
  args: { report: bullish },
  play: async ({ canvas }) => {
    await expect(canvas.getByText(bullish.headline)).toBeVisible();
  },
};

/** Same shape, bearish bias — drives the rose-toned chip and signal color. */
export const Bearish: Story = {
  args: {
    report: {
      ...bullish,
      bias: "bearish",
      headline: "Distribution under the 50-day",
      signals: [{ ...bullish.signals[0], bias: "bearish", confidence: 0.61 }],
    },
  },
};

/** Sparse report — only headline and summary, no signals/levels/risks sections. */
export const Minimal: Story = {
  args: {
    report: {
      headline: "Quiet, range-bound tape",
      bias: "neutral",
      summary: "Nothing actionable; waiting for a catalyst.",
      signals: [],
      key_levels: [],
      risks: [],
      next_check_in: "end of day",
    },
  },
};
