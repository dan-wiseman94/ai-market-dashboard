import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import type { WarRoomVerdictContent } from "@/api/observation";
import WarRoomVerdictBody from "./WarRoomVerdictBody";

const verdict: WarRoomVerdictContent = {
  verdict: "bull case stronger",
  confidence: 0.68,
  strongest_bull: "Breadth confirmed the move and the sector is leading, not lagging.",
  strongest_bear: "Rates back up would compress the multiple faster than earnings can catch it.",
  what_would_change_my_mind: "A daily close back inside the range on rising volume.",
  ai: { provider: "claude", model: "claude-opus-5" },
};

const meta = {
  title: "Strategy/WarRoomVerdictBody",
  component: WarRoomVerdictBody,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "The synthesizer's read on a bull/bear/skeptic debate: a one-line verdict with calibrated confidence, the strongest point from each side, and the falsifier — attributed to the provider that reached it.",
      },
    },
  },
  argTypes: {
    verdict: { control: "object", description: "The stored WarRoomRun.verdict payload." },
  },
} satisfies Meta<typeof WarRoomVerdictBody>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A confident verdict with both sides and the falsifier. */
export const BullCaseStronger: Story = {
  args: { verdict },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("68% conf")).toBeVisible();
  },
};

/** A balanced call with no confidence recorded — the pill simply drops out. */
export const Balanced: Story = {
  args: {
    verdict: { ...verdict, verdict: "balanced", confidence: undefined, ai: undefined },
  },
};
