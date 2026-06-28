import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { BookTile } from "./BookTile";

const meta = {
  title: "Content/BookTile",
  component: BookTile,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Dashboard tile linking to `/book`: shows the whole-book alignment reading and concentration (HHI). A `misaligned` reading is copper-toned; with no snapshot it shows a fallback line.",
      },
    },
  },
  argTypes: {
    book: { control: "object", description: "Book reading: alignment, HHI concentration, and as-of timestamp." },
  },
} satisfies Meta<typeof BookTile>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A healthy book: aligned reading plus the HHI concentration line. */
export const Aligned: Story = {
  args: {
    book: { hhi: 0.18, alignment: "aligned", as_of: "2026-06-27T13:30:00Z" },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Book risk")).toBeVisible();
    await expect(canvas.getByText("aligned")).toBeVisible();
    await expect(canvas.getByText("HHI 0.18")).toBeVisible();
  },
};

/** A concentrated book flagged `misaligned` — the reading renders copper-toned. */
export const Misaligned: Story = {
  args: {
    book: { hhi: 0.42, alignment: "misaligned", as_of: "2026-06-27T13:30:00Z" },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("misaligned")).toBeVisible();
    await expect(canvas.getByText("HHI 0.42")).toBeVisible();
  },
};

/** No book snapshot yet — the eyebrow stays but the body falls back. */
export const NoSnapshot: Story = {
  args: {
    book: { hhi: null, alignment: null, as_of: null },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No snapshot yet")).toBeVisible();
    await expect(canvas.queryByText(/^HHI/)).toBeNull();
  },
};
