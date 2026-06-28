import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent } from "storybook/test";
import { ToolCallTrace, type ToolCallRecord } from "./ToolCallTrace";

const calls: ToolCallRecord[] = [
  {
    toolUseId: "tu_1",
    name: "get_quote",
    input: { ticker: "AAPL" },
    ok: true,
    latencyMs: 142,
    result: { last: 196.21, change: 1.4 },
  },
  {
    toolUseId: "tu_2",
    name: "get_chain",
    input: { ticker: "AAPL", expiry: "2026-07-17" },
    ok: false,
    error: "rate limited",
    latencyMs: 873,
  },
];

const meta = {
  title: "Thread/ToolCallTrace",
  component: ToolCallTrace,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Collapsible rows for each AI tool call/result, color-toned by success and expandable to show raw input/result JSON.",
      },
    },
  },
} satisfies Meta<typeof ToolCallTrace>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { calls },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("get_quote")).toBeVisible();
    await expect(canvas.getByText("get_chain")).toBeVisible();
    await expect(canvas.getByText("142 ms")).toBeVisible();
    await expect(canvas.getByText(/rate limited/)).toBeVisible();
  },
};

export const ExpandRow: Story = {
  args: { calls: [calls[0]] },
  play: async ({ canvas }) => {
    const button = canvas.getByRole("button");
    await userEvent.click(button);
    await expect(await canvas.findByText(/"last": 196.21/)).toBeVisible();
  },
};

export const ErrorOnly: Story = {
  args: { calls: [calls[1]] },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("get_chain")).toBeVisible();
    await expect(canvas.getByText(/✗ rate limited/)).toBeVisible();
  },
};
