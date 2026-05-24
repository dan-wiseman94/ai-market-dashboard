import type { Meta, StoryObj } from "@storybook/react-vite";
import { Skeleton, SkeletonRows } from "./Skeleton";

const meta = {
  title: "Primitives/Skeleton",
  component: Skeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A single shimmer bar — size it with Tailwind classes. */
export const Line: Story = {
  args: { className: "h-4 w-64" },
};

/** A larger block placeholder, e.g. a card or chart slot. */
export const Block: Story = {
  args: { className: "h-32 w-80" },
};

/** `SkeletonRows` — a stack of full-width rows for list/table loading states. */
export const Rows: Story = {
  render: () => <SkeletonRows rows={5} />,
};
