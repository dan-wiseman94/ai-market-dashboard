import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { RegimeTile } from "./RegimeTile";

const meta = {
  title: "Content/RegimeTile",
  component: RegimeTile,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Dashboard tile for the whole-book market regime. Takes a `regime` prop (composite stance + drivers) and tones the composite by stance; with no composite it shows the 'No reading yet' empty state. Links to `/regime`.",
      },
    },
  },
} satisfies Meta<typeof RegimeTile>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Risk-On reading: emerald-toned composite plus the leading driver. */
export const RiskOn: Story = {
  args: {
    regime: {
      composite: "Risk-On",
      drivers: ["VIX 13.2 — Calm", "Breadth broadening"],
      as_of: "2026-06-01T12:00:00Z",
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Market regime")).toBeVisible();
    await expect(canvas.getByText("Risk-On")).toBeVisible();
    await expect(canvas.getByText("VIX 13.2 — Calm")).toBeVisible();
  },
};

/** Risk-Off reading: copper-toned composite. */
export const RiskOff: Story = {
  args: {
    regime: {
      composite: "Risk-Off",
      drivers: ["VIX 24 — Elevated"],
      as_of: "2026-06-01T12:00:00Z",
    },
  },
};

/** Stress reading: loss-toned composite for the most defensive stance. */
export const Stress: Story = {
  args: {
    regime: {
      composite: "Stress",
      drivers: ["Credit spreads widening"],
      as_of: "2026-06-01T12:00:00Z",
    },
  },
};

/** No composite yet — the "No reading yet" empty state. */
export const NoReading: Story = {
  args: {
    regime: { composite: null, drivers: [], as_of: null },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("No reading yet")).toBeVisible();
  },
};
