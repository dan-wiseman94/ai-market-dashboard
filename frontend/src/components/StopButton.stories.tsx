import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
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
export const Default: Story = {};
