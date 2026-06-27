import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent } from "storybook/test";
import StopButton from "./StopButton";

const meta = {
  title: "Primitives/StopButton",
  component: StopButton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { onStop: fn() },
} satisfies Meta<typeof StopButton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Halts an in-flight AI generation; `onStop` fires the stop request. */
export const Default: Story = {
  play: async ({ canvas }) => {
    const button = canvas.getByRole("button", { name: "Stop generation" });
    await expect(button).toBeVisible();
    await expect(canvas.getByText("Stop")).toBeVisible();
  },
};

/** Clicking the button invokes the `onStop` callback. */
export const Clicked: Story = {
  args: { onStop: fn() },
  play: async ({ canvas, args }) => {
    const button = canvas.getByRole("button", { name: "Stop generation" });
    await userEvent.click(button);
    await expect(args.onStop).toHaveBeenCalledTimes(1);
  },
};
