import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import CapMeter from "./CapMeter";

const meta = {
  title: "Primitives/CapMeter",
  component: CapMeter,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A spend-vs-cap meter: a thin bar plus `$spent / $cap` and a rounded percentage. The bar and percentage shift tone with `pct` — gain under 80%, copper at 80%+, loss at 100%+ — and the fill width clamps at 100%.",
      },
    },
  },
  argTypes: {
    label: { control: "text", description: "Short uppercase label shown at the left." },
    cap: { control: "text", description: "Cap amount, pre-formatted (no `$`)." },
    spent: { control: "text", description: "Spent amount, pre-formatted (no `$`)." },
    pct: {
      control: { type: "range", min: 0, max: 1.5, step: 0.01 },
      description: "Spent / cap ratio. Drives the fill width (clamped) and the tone.",
    },
  },
} satisfies Meta<typeof CapMeter>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Well under the cap — gain-toned bar at a quarter full. */
export const Healthy: Story = {
  args: { label: "Monthly", cap: "50.00", spent: "12.40", pct: 0.25 },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Monthly")).toBeVisible();
    await expect(canvas.getByText("$12.40 / $50.00")).toBeVisible();
    await expect(canvas.getByText("25%")).toBeVisible();
    const fill = canvas.getByTestId("capmeter-fill");
    await expect(fill.style.width).toBe("25%");
  },
};

/** Crossing the 80% copper threshold — the warning tone. */
export const Warning: Story = {
  args: { label: "Daily", cap: "5.00", spent: "4.30", pct: 0.86 },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("86%")).toBeVisible();
    await expect(canvas.getByText("$4.30 / $5.00")).toBeVisible();
  },
};

/** Over the cap — loss tone and the fill clamped at 100% even though pct is 1.15. */
export const Exceeded: Story = {
  args: { label: "Monthly", cap: "50.00", spent: "57.50", pct: 1.15 },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("115%")).toBeVisible();
    const fill = canvas.getByTestId("capmeter-fill");
    await expect(fill.style.width).toBe("100%");
  },
};
