import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import OptionChainTable from "./OptionChainTable";

const meta = {
  title: "Market/OptionChainTable",
  component: OptionChainTable,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A captured option chain: expiry-tab selector over a calls / strike / puts grid. The strike nearest the underlying is highlighted as ATM; missing legs render em-dashes; a null payload shows the \"No chain data.\" empty state.",
      },
    },
  },
} satisfies Meta<typeof OptionChainTable>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Two expiries; ATM strike near the underlying is highlighted. Clicking a tab switches the grid. */
export const Populated: Story = {
  args: {
    payload: {
      ticker: "AAPL",
      underlying_last: "190.00",
      expiries: {
        "2026-07-17": {
          calls: [
            { strike: "185", bid: "6.10", ask: "6.30", delta: "0.72", iv: "0.28", volume: 1200, oi: 4400 },
            { strike: "190", bid: "3.05", ask: "3.20", delta: "0.51", iv: "0.26", volume: 2100, oi: 8800 },
            { strike: "195", bid: "1.20", ask: "1.35", delta: "0.29", iv: "0.27", volume: 900, oi: 3300 },
          ],
          puts: [
            { strike: "185", bid: "1.05", ask: "1.18", delta: "-0.28", iv: "0.29" },
            { strike: "190", bid: "2.90", ask: "3.05", delta: "-0.49", iv: "0.27" },
            { strike: "195", bid: "5.80", ask: "6.00", delta: "-0.71", iv: "0.28" },
          ],
        },
        "2026-08-21": {
          calls: [
            { strike: "190", bid: "5.40", ask: "5.60", delta: "0.55", iv: "0.30" },
          ],
          puts: [
            { strike: "190", bid: "5.10", ask: "5.30", delta: "-0.45", iv: "0.31" },
          ],
        },
      },
    },
  },
  play: async ({ canvas, userEvent }) => {
    await expect(canvas.getByText("190.00")).toBeVisible();
    await expect(canvas.getByText("call bid")).toBeVisible();
    await expect(canvas.getByText("0.72")).toBeVisible();
    await userEvent.click(canvas.getByRole("button", { name: "2026-08-21" }));
    await expect(canvas.getByText("5.40")).toBeVisible();
  },
};

/** A leg missing on one side renders an em-dash placeholder rather than a blank cell. */
export const MissingLegs: Story = {
  args: {
    payload: {
      ticker: "SPY",
      underlying_last: "511.00",
      expiries: {
        "2026-07-17": {
          calls: [{ strike: "510", bid: "4.10", ask: "4.30", delta: "0.58", iv: "0.14" }],
          puts: [{ strike: "515", bid: "5.10", ask: "5.40", delta: "-0.62", iv: "0.15" }],
        },
      },
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("511.00")).toBeVisible();
    await expect(canvas.getAllByText("—").length).toBeGreaterThan(0);
  },
};

/** Null payload — the "No chain data." empty state. */
export const Empty: Story = {
  args: { payload: null },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No chain data.")).toBeVisible();
  },
};
