import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import type { Condition, Leaf } from "@/api/triggers";
import RuleBuilder from "./RuleBuilder";

const leaves: Leaf[] = [
  { metric: "price", ticker: "AAPL", op: ">", value: 200 },
  { metric: "pct_change", ticker: "SPY", op: "<", value: -0.02, window: "1d" },
];

const condition: Condition = { all: leaves };

// The leaf RuleBuilder appends when "+ Add condition" is clicked (EMPTY_LEAF).
const ADDED_LEAF: Leaf = { metric: "price", ticker: "SPY", op: ">", value: 0 };

const meta = {
  title: "Observer/RuleBuilder",
  component: RuleBuilder,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Interactive editor for the event-trigger DSL: a top-level `all`/`any` group operator over a list of leaf conditions (metric · ticker · op · value · window). Fully prop-driven — every edit re-emits the whole `Condition` through `onChange`; the parent owns the value.",
      },
    },
  },
  args: { onChange: fn() },
  argTypes: {
    value: { control: false, description: "The current DSL condition (controlled)." },
    onChange: { description: "Fired with the next full `Condition` on every edit." },
    readOnly: { control: "boolean", description: "Hide edit affordances and disable inputs." },
  },
} satisfies Meta<typeof RuleBuilder>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An `all` group with two leaves; clicking "+ Add condition" re-emits the group with a default leaf appended. */
export const Default: Story = {
  args: { value: condition },
  play: async ({ canvas, userEvent, args }) => {
    await expect(canvas.getByText(/price of AAPL is greater than 200/i)).toBeVisible();
    await expect(canvas.getByText(/SPY moved/i)).toBeVisible();

    await userEvent.click(canvas.getByRole("button", { name: /add condition/i }));
    await expect(args.onChange).toHaveBeenCalledWith({ all: [...leaves, ADDED_LEAF] });
  },
};

/** Switching the group operator from `all` to `any` re-emits the same leaves under an `any` key. */
export const ToggleOperator: Story = {
  args: { value: condition },
  play: async ({ canvas, userEvent, args }) => {
    const op = canvas.getByLabelText("group operator");
    await userEvent.selectOptions(op, "any");
    await expect(args.onChange).toHaveBeenCalledWith({ any: leaves });
  },
};

/** Read-only: the operator select is disabled and the add/remove affordances are gone. */
export const ReadOnly: Story = {
  args: { value: condition, readOnly: true },
  play: async ({ canvas }) => {
    await expect(canvas.getByLabelText("group operator")).toBeDisabled();
    await expect(canvas.queryByRole("button", { name: /add condition/i })).toBeNull();
    await expect(canvas.queryByRole("button", { name: /remove condition/i })).toBeNull();
  },
};
