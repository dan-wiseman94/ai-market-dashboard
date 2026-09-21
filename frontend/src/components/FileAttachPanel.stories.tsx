import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import { FileAttachPanel } from "./FileAttachPanel";

const FILES = [
  {
    id: 1,
    anthropic_id: "file_a",
    filename: "AAPL-10K-FY2025.pdf",
    kind: "filing",
    ticker: "AAPL",
    mime: "application/pdf",
    size: 2_400_000,
  },
  {
    id: 2,
    anthropic_id: "file_b",
    filename: "q3-earnings-call.txt",
    kind: "transcript",
    ticker: "AAPL",
    mime: "text/plain",
    size: 48_000,
  },
];

const meta = {
  title: "Thread/FileAttachPanel",
  component: FileAttachPanel,
  tags: ["ai-generated"],
  args: { threadId: 7, files: FILES, onAttach: fn(), onDelete: fn() },
  parameters: {
    docs: {
      description: {
        component:
          "Uploaded documents for a thread. Attach pushes the file into the " +
          "conversation as a document block; Delete removes it here AND upstream " +
          "at the provider, so the caller confirms first. Attachments are " +
          "Claude-only — when the thread's profile runs elsewhere the panel is " +
          "handed a reason and the attach buttons go dead rather than no-op.",
      },
    },
  },
} satisfies Meta<typeof FileAttachPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithFiles: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Attach AAPL-10K-FY2025.pdf" })).toBeEnabled();
  },
};

/** Without an `onDelete` handler no delete control is offered at all. */
export const AttachOnly: Story = {
  args: { onDelete: undefined },
  play: async ({ canvas }) => {
    await expect(canvas.queryByRole("button", { name: /^Delete/ })).toBeNull();
  },
};

/** A non-Claude profile: attach is disabled and the reason is its tooltip. */
export const ProviderCannotReadDocuments: Story = {
  args: {
    attachDisabledReason:
      "This thread's profile runs on OpenAI, which can't read attached documents — files are Claude-only.",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Attach q3-earnings-call.txt" })).toBeDisabled();
  },
};

export const Empty: Story = {
  args: { files: [] },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No files yet")).toBeVisible();
  },
};
