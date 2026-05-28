import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import type { BranchState } from "@/hooks/useBranchState";
import CompareTotalsStrip from "./CompareTotalsStrip";

const meta = {
  title: "Thread/CompareTotalsStrip",
  component: CompareTotalsStrip,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component: "Footer strip summing cost across Compare branches and reporting the slowest leg.",
      },
    },
  },
  argTypes: {
    state: { control: "object", description: "Branch id → BranchState (cost, durationMs, …)." },
  },
} satisfies Meta<typeof CompareTotalsStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

const twoBranches: Record<number, BranchState> = {
  1: { status: "done", provider: "claude", model: "claude-opus-4-8", cost: 0.0123, durationMs: 4200 },
  2: { status: "done", provider: "openai", model: "gpt-5", cost: 0.0218, durationMs: 6100 },
};

/** Sums every branch's cost and reports the slowest leg. */
export const WithCosts: Story = {
  args: { state: twoBranches },
  play: async ({ canvas }) => {
    // Total = 0.0123 + 0.0218, formatted by usd().
    await expect(canvas.getByText("$0.0341")).toBeVisible();
  },
};

/** A single finished branch — no "slowest" segment when only one timing exists. */
export const SingleBranch: Story = {
  args: {
    state: {
      1: { status: "done", provider: "claude", model: "claude-opus-4-8", cost: 0.0101, durationMs: 0 },
    },
  },
};
