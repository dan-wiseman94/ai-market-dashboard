import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import StreamingMessage from "./StreamingMessage";

const meta = {
  title: "Thread/StreamingMessage",
  component: StreamingMessage,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "One chat turn — user (serif body, copper rule), assistant (markdown body, provider/model label, cost pill), mid-stream, or failed.",
      },
    },
  },
  argTypes: {
    role: { control: "inline-radio", options: ["user", "assistant", "system"], description: "Message author." },
    status: { control: "inline-radio", options: ["done", "streaming", "failed"], description: "Lifecycle state." },
    text: { control: "text", description: "Markdown body (assistant) or plain text (user)." },
    provider: { control: "text", description: "Provider label; capitalized in the header." },
    model: { control: "text", description: "Model id, shown beside the provider." },
    cost: { control: "text", description: "Cost in USD (string); formatted into the header pill." },
    error: { control: "text", description: "Error message, shown when status is failed." },
    bare: { control: "boolean", description: "Drop the outer surface (caller provides one)." },
  },
} satisfies Meta<typeof StreamingMessage>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The user turn — copper rule, serif body, "You" eyebrow. */
export const UserTurn: Story = {
  args: {
    role: "user",
    text: "What does breadth look like under the surface today?",
  },
};

/** A finished assistant turn with markdown body, provider/model label, and a cost pill. */
export const AssistantWithCost: Story = {
  args: {
    role: "assistant",
    provider: "claude",
    model: "claude-opus-4-7",
    status: "done",
    cost: "0.0123",
    text: "Breadth is **firming**: advancers lead 2:1 while the index treads water.",
  },
  play: async ({ canvas }) => {
    // `cost` is formatted through `usd()` and rendered in the header pill.
    await expect(canvas.getByText("$0.0123")).toBeVisible();
  },
};

/** Mid-stream: the "Transmitting…" status and pulsing caret are shown. */
export const Streaming: Story = {
  args: {
    role: "assistant",
    provider: "openai",
    model: "gpt-5",
    status: "streaming",
    text: "Scanning the tape",
  },
};

/** A failed generation surfaces the error text beside a loss-toned pill. */
export const Failed: Story = {
  args: {
    role: "assistant",
    status: "failed",
    text: "",
    error: "Rate limit exceeded — retry in 30s",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText(/rate limit exceeded/i)).toBeVisible();
  },
};
