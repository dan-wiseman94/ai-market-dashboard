import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import BranchTabs from "./BranchTabs";

const meta = {
  component: BranchTabs,
  tags: ["ai-generated"],
  parameters: { layout: "padded" },
  args: { onSelect: fn(), activeId: 1 },
} satisfies Meta<typeof BranchTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Two finished branches; clicking a tab routes its id to `onSelect`. */
export const Default: Story = {
  args: {
    activeId: 1,
    branches: [
      { id: 1, label: "Claude", status: "done", cost: 0.0123 },
      { id: 2, label: "GPT-5", status: "done", cost: 0.0218 },
    ],
  },
  play: async ({ canvas, userEvent, args }) => {
    await userEvent.click(canvas.getByRole("button", { name: /gpt-5/i }));
    await expect(args.onSelect).toHaveBeenCalledWith(2);
  },
};

/** A branch still streaming shows the pulsing "streaming" marker instead of a cost. */
export const Streaming: Story = {
  args: {
    activeId: 3,
    branches: [
      { id: 3, label: "Local", status: "streaming" },
      { id: 1, label: "Claude", status: "done", cost: 0.0098 },
    ],
  },
};

/** A failed branch is flagged with a loss-toned ✗. */
export const Failed: Story = {
  args: {
    activeId: 1,
    branches: [
      { id: 1, label: "Claude", status: "done", cost: 0.0101 },
      { id: 2, label: "GPT-5", status: "failed" },
    ],
  },
};

/**
 * Proves the shared preview actually loaded `globals.css`: the active tab uses
 * the `.text-copper-200` utility (`--copper-200: #f1ca8b`). Without the
 * stylesheet this resolves to the default text color and the assertion fails.
 */
export const CssCheck: Story = {
  args: {
    activeId: 1,
    branches: [{ id: 1, label: "Claude", status: "done", cost: 0.0123 }],
  },
  play: async ({ canvas }) => {
    const active = canvas.getByRole("button", { name: /claude/i });
    await expect(getComputedStyle(active).color).toBe("rgb(241, 202, 139)");
  },
};
