import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import LeafRow from "./LeafRow";

const meta = {
  title: "Observer/LeafRow",
  component: LeafRow,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A single DSL leaf row in the RuleBuilder: metric/operator/value selectors, conditional ticker, window and indicator-params sub-forms, plus a live natural-language description of the leaf.",
      },
    },
  },
  args: { onChange: fn(), onRemove: fn() },
  argTypes: {
    leaf: { control: false, description: "The DSL leaf (metric, op, value, optional ticker/window/params)." },
    onChange: { description: "Fired with the next leaf whenever a field changes." },
    onRemove: { description: "Fired when the ✕ remove button is clicked." },
    readOnly: { control: "boolean", description: "Disables every input and hides the remove button + params form." },
  },
} satisfies Meta<typeof LeafRow>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A plain price leaf: ticker input is shown, the description reads it back in words, and the ✕ routes to `onRemove`. */
export const Price: Story = {
  args: {
    leaf: { metric: "price", ticker: "AAPL", op: ">", value: 200 },
  },
  play: async ({ canvas, userEvent, args }) => {
    await expect(canvas.getByText("price of AAPL is greater than 200")).toBeVisible();
    await expect(canvas.getByLabelText("ticker")).toHaveValue("AAPL");
    await userEvent.click(canvas.getByRole("button", { name: /remove condition/i }));
    await expect(args.onRemove).toHaveBeenCalled();
  },
};

/** A pct_change leaf exposes the window selector; the description folds the fraction into a percentage magnitude. */
export const PctChange: Story = {
  args: {
    leaf: { metric: "pct_change", ticker: "SPY", op: ">=", value: -0.05, window: "5m" },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByLabelText("window")).toBeVisible();
    await expect(canvas.getByText("SPY moved ≥5% over 5m")).toBeVisible();
  },
};

/** An indicator metric (rsi) reveals the period params sub-form alongside ticker + window. */
export const Indicator: Story = {
  args: {
    leaf: { metric: "rsi", ticker: "NVDA", op: ">", value: 70, window: "1h", params: { period: 14 } },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByLabelText("period")).toHaveValue(14);
    await expect(canvas.getByText("rsi of NVDA is greater than 70")).toBeVisible();
  },
};

/** Read-only mode disables the inputs and drops both the remove button and the params sub-form. */
export const ReadOnly: Story = {
  args: {
    leaf: { metric: "vix", op: ">", value: 30 },
    readOnly: true,
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByRole("button", { name: /remove condition/i })).toBeNull();
    await expect(canvas.getByLabelText("metric")).toBeDisabled();
    await expect(canvas.getByText("VIX is greater than 30")).toBeVisible();
  },
};
