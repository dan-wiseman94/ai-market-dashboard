import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { DeskTile } from "./DeskTile";

const meta = {
  title: "Content/DeskTile",
  component: DeskTile,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Dashboard tile linking to The Desk. Given an unread count it shows the copper `<n> new` headline plus the latest flag; with zero unread it falls back to the muted \"No new flags\" state.",
      },
    },
  },
  argTypes: {
    desk: { control: "object", description: "Unread flag count plus the latest flag summary (or null)." },
  },
} satisfies Meta<typeof DeskTile>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Unread flags present — copper headline plus the latest flag line. */
export const WithFlags: Story = {
  args: { desk: { unread: 3, latest: "NVDA unusual call volume vs OI" } },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("The Desk")).toBeVisible();
    await expect(canvas.getByText("3 new")).toBeVisible();
    await expect(canvas.getByText("NVDA unusual call volume vs OI")).toBeVisible();
  },
};

/** Unread count with no summary — the headline shows, the latest line is omitted. */
export const FlagsNoSummary: Story = {
  args: { desk: { unread: 1, latest: null } },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("1 new")).toBeVisible();
    await expect(canvas.queryByText(/No new flags/i)).not.toBeInTheDocument();
  },
};

/** Nothing unread — the muted "No new flags" empty state. */
export const Empty: Story = {
  args: { desk: { unread: 0, latest: null } },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No new flags")).toBeVisible();
  },
};
