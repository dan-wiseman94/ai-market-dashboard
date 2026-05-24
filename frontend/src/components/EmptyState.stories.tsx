import type { Meta, StoryObj } from "@storybook/react-vite";
import { EmptyState } from "./EmptyState";

const meta = {
  title: "Primitives/EmptyState",
  component: EmptyState,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Just a heading — the minimal "nothing here" state. */
export const TitleOnly: Story = {
  args: { title: "No snapshots yet" },
};

/** Heading plus explanatory body copy. */
export const WithBody: Story = {
  args: {
    title: "No snapshots yet",
    body: "Capture a market snapshot to send it to an AI for observations.",
  },
};

/** Full call-to-action variant with an action slot. */
export const WithAction: Story = {
  args: {
    title: "No snapshots yet",
    body: "Capture a market snapshot to send it to an AI for observations.",
    action: (
      <button className="ledger-pill hover:border-copper-500/60 hover:text-copper-200 transition-colors">
        Capture snapshot
      </button>
    ),
  },
};
