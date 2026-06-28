import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import QuoteCell from "./QuoteCell";

const meta = {
  title: "Market/QuoteCell",
  component: QuoteCell,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Renders a quote's last price plus its percent change (green when up, red when down); shows an em dash when the quote is missing or has no last price.",
      },
    },
  },
  argTypes: {
    q: { description: "The quote to render, or undefined for a placeholder dash." },
  },
} satisfies Meta<typeof QuoteCell>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A positive change renders the price and a leading-plus percent. */
export const Up: Story = {
  args: {
    q: { last: 187.42, bid: 187.4, ask: 187.45, volume: 12_000_000, high: 188, low: 185, pct_change: 1.23 },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("187.42")).toBeVisible();
    await expect(canvas.getByText("+1.23%")).toBeVisible();
  },
};

/** A negative change renders the percent without a plus sign. */
export const Down: Story = {
  args: {
    q: { last: 94.5, bid: 94.4, ask: 94.6, volume: 8_000_000, high: 97, low: 94, pct_change: -2.5 },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("94.50")).toBeVisible();
    await expect(canvas.getByText("-2.50%")).toBeVisible();
  },
};

/** A null pct_change renders the price with an empty percent span. */
export const PriceOnly: Story = {
  args: {
    q: { last: 42, bid: null, ask: null, volume: null, high: null, low: null, pct_change: null },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("42.00")).toBeVisible();
  },
};

/** An undefined quote renders the em-dash placeholder. */
export const Missing: Story = {
  args: { q: undefined },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("—")).toBeVisible();
  },
};
