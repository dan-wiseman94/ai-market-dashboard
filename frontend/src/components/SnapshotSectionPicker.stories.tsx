import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import SnapshotSectionPicker from "./SnapshotSectionPicker";

const meta = {
  title: "Snapshot/SnapshotSectionPicker",
  component: SnapshotSectionPicker,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component: "Checkbox set choosing which sections a snapshot captures; toggling emits the next selection.",
      },
    },
  },
  args: { onChange: fn() },
  argTypes: {
    value: { control: "object", description: "Currently selected section keys." },
    onChange: { description: "Fired with the next selection array." },
  },
} satisfies Meta<typeof SnapshotSectionPicker>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Two sections pre-selected; ticking another appends its key via `onChange`. */
export const Default: Story = {
  args: { value: ["quotes", "ohlc"] },
  play: async ({ canvas, userEvent, args }) => {
    await userEvent.click(canvas.getByLabelText("News"));
    await expect(args.onChange).toHaveBeenCalledWith(["quotes", "ohlc", "news"]);
  },
};

/** Every section enabled. */
export const AllSelected: Story = {
  args: {
    value: ["quotes", "ohlc", "positions", "breadth", "notes", "chain", "news", "image"],
  },
};
