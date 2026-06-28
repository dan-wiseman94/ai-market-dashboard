import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { RelativeTime } from "./RelativeTime";

const meta = {
  title: "Primitives/RelativeTime",
  component: RelativeTime,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A relative timestamp rendered in a semantic <time> element with a maskable data-testid, so the e2e visual lane can mask its inherently non-deterministic text.",
      },
    },
  },
} satisfies Meta<typeof RelativeTime>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Past time with an " ago" suffix. */
export const Ago: Story = {
  args: { iso: "2026-06-01T12:00:00Z", suffix: " ago" },
  play: async ({ canvas }) => {
    const el = canvas.getByTestId("relative-time");
    await expect(el.tagName.toLowerCase()).toBe("time");
    await expect(el).toHaveAttribute("datetime", "2026-06-01T12:00:00Z");
    await expect(el.textContent ?? "").toMatch(/ago$/);
  },
};

/** No suffix — the caller supplies surrounding text (e.g. "refreshes in …"). */
export const NoSuffix: Story = {
  args: { iso: "2026-06-01T12:00:00Z" },
  play: async ({ canvas }) => {
    await expect(canvas.getByTestId("relative-time").textContent ?? "").not.toMatch(/ago$/);
  },
};
