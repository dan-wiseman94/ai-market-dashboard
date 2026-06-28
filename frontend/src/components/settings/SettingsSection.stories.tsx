import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import SettingsSection from "./SettingsSection";

const meta = {
  title: "Primitives/SettingsSection",
  component: SettingsSection,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A settings panel wrapper: a display-font title, an optional muted description, an optional right-aligned action slot, and a vertically spaced children area.",
      },
    },
  },
  args: {
    title: "Cost caps",
    children: <div className="text-ink-200 text-sm">Section body content.</div>,
  },
  argTypes: {
    title: { control: "text", description: "Heading shown in the display font." },
    description: { control: "text", description: "Optional muted sub-line under the title." },
    action: { control: false, description: "Optional right-aligned action node in the header." },
    children: { control: false, description: "Section body, rendered in a spaced stack." },
  },
} satisfies Meta<typeof SettingsSection>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Title plus a description line and a body. */
export const Default: Story = {
  args: {
    description: "Monthly spend ceilings applied across every provider.",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { name: "Cost caps" })).toBeVisible();
    await expect(
      canvas.getByText("Monthly spend ceilings applied across every provider."),
    ).toBeVisible();
  },
};

/** No description — only the title renders above the body. */
export const TitleOnly: Story = {
  args: {
    title: "Data sources",
    description: undefined,
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { name: "Data sources" })).toBeVisible();
    await expect(canvas.queryByText("Monthly spend ceilings", { exact: false })).toBeNull();
  },
};

/** An action node sits at the right edge of the header. */
export const WithAction: Story = {
  args: {
    title: "Providers",
    description: "Connected AI providers and their keys.",
    action: (
      <button type="button" className="rounded border border-ink-700 px-3 py-1 text-sm text-ink-100">
        Add provider
      </button>
    ),
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Add provider" })).toBeVisible();
  },
};
