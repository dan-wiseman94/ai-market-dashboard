import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { StatusBadge, VerdictBadge } from "./ThesisBadges";
import type { PostMortemVerdict, ThesisStatus } from "@/api/thesis";

const meta = {
  title: "Content/ThesisBadges",
  component: StatusBadge,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Small inline badges that render a thesis lifecycle status or a post-mortem verdict with color-coded styling.",
      },
    },
  },
  argTypes: {
    status: {
      control: "select",
      options: [
        "open",
        "closed_win",
        "closed_loss",
        "closed_scratch",
        "invalidated",
      ] satisfies ThesisStatus[],
    },
  },
} satisfies Meta<typeof StatusBadge>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {
  args: { status: "open" },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Open")).toBeVisible();
    await expect(canvas.getByTestId("status-badge-open")).toBeVisible();
  },
};

export const Win: Story = {
  args: { status: "closed_win" },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Win")).toBeVisible();
  },
};

export const Loss: Story = {
  args: { status: "closed_loss" },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Loss")).toBeVisible();
  },
};

export const Invalidated: Story = {
  args: { status: "invalidated" },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Invalidated")).toBeVisible();
  },
};

export const AllStatuses: Story = {
  args: { status: "open" },
  render: () => {
    const statuses: ThesisStatus[] = [
      "open",
      "closed_win",
      "closed_loss",
      "closed_scratch",
      "invalidated",
    ];
    return (
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {statuses.map((s) => (
          <StatusBadge key={s} status={s} />
        ))}
      </div>
    );
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Open")).toBeVisible();
    await expect(canvas.getByText("Scratch")).toBeVisible();
    await expect(canvas.getByText("Invalidated")).toBeVisible();
  },
};

export const Verdicts: Story = {
  args: { status: "closed_win" },
  render: () => {
    const verdicts: PostMortemVerdict[] = [
      "correct",
      "incorrect",
      "mixed",
      "inconclusive",
      "",
    ];
    return (
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {verdicts.map((v) => (
          <VerdictBadge key={v || "empty"} verdict={v} />
        ))}
      </div>
    );
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Correct")).toBeVisible();
    await expect(canvas.getByText("Incorrect")).toBeVisible();
    await expect(canvas.getByTestId("verdict-badge-empty")).toBeVisible();
  },
};
