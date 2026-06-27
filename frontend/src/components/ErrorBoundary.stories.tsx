import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { ErrorBoundary } from "./ErrorBoundary";

function Boom({ message }: { message: string }): never {
  throw new Error(message);
}

const meta = {
  title: "Primitives/ErrorBoundary",
  component: ErrorBoundary,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Class error boundary that traps render errors in its subtree, shows a recoverable fallback, and clears the error when resetKey changes.",
      },
    },
  },
} satisfies Meta<typeof ErrorBoundary>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Healthy: Story = {
  args: {
    children: <p>All systems nominal.</p>,
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("All systems nominal.")).toBeVisible();
  },
};

export const Caught: Story = {
  args: {
    children: <Boom message="Snapshot capture failed" />,
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Something went wrong.")).toBeVisible();
    await expect(canvas.getByText("Snapshot capture failed")).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Reload" })).toBeVisible();
  },
};
