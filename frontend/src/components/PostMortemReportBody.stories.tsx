import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import type { PostMortemReportContent } from "@/api/observation";
import PostMortemReportBody from "./PostMortemReportBody";

const report: PostMortemReportContent = {
  summary:
    "The breakout held and the position reached its first target, but the add was late enough to halve the edge.",
  what_worked: ["Waited for the retest instead of chasing", "Invalidation was priced, not vibes"],
  what_missed: ["Added 40 minutes after the trigger", "Ignored the widening spread"],
  lessons: ["Size the add at the trigger or skip it"],
  would_repeat: true,
  ai: { provider: "openai", model: "gpt-5.6-sol" },
};

const meta = {
  title: "Thesis/PostMortemReportBody",
  component: PostMortemReportBody,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "The AI narrative layered on a post-mortem's deterministic verdict: summary, what worked, what missed, lessons, and whether the trader would repeat the setup — attributed to the provider that wrote it.",
      },
    },
  },
  argTypes: {
    report: { control: "object", description: "The stored PostMortem.report payload." },
  },
} satisfies Meta<typeof PostMortemReportBody>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A full narrative with both columns populated. */
export const WouldRepeat: Story = {
  args: { report },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("would repeat")).toBeVisible();
  },
};

/** The other verdict, with empty sections hidden rather than rendered blank. */
export const WouldNotRepeat: Story = {
  args: {
    report: { ...report, would_repeat: false, what_worked: [], lessons: [] },
  },
};
