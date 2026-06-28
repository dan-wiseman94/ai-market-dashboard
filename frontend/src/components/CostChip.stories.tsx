import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse, delay } from "msw";
import type { CostsToday } from "@/api/costs";
import CostChip from "./CostChip";

const COSTS_TODAY_URL = "/api/costs/today/";

const today: CostsToday = {
  total_usd: "12.3456",
  by_provider: [
    {
      provider: "anthropic",
      cost_usd: "12.3456",
      runs: 4,
      input_tokens: 18_200,
      output_tokens: 3_410,
      cached_tokens: 9_000,
    },
  ],
};

const meta = {
  title: "Primitives/CostChip",
  component: CostChip,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "A nav pill that shows today's AI spend and links to the costs page. Fetches `/api/costs/today/` via react-query; these stories mock that endpoint with MSW.",
      },
    },
  },
} satisfies Meta<typeof CostChip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Spend today — the dollar value renders to four decimals via `usd()`. */
export const Populated: Story = {
  args: {},
  parameters: {
    msw: { handlers: [http.get(COSTS_TODAY_URL, () => HttpResponse.json(today))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("$12.3456")).toBeVisible();
    await expect(canvas.getByText("Today")).toBeVisible();
    const link = canvas.getByRole("link", { name: /Today/ });
    await expect(link).toHaveAttribute("href", "/costs");
  },
};

/** No spend yet — falls back to the zeroed amount. */
export const Zero: Story = {
  args: {},
  parameters: {
    msw: {
      handlers: [
        http.get(COSTS_TODAY_URL, () =>
          HttpResponse.json({ total_usd: "0", by_provider: [] } satisfies CostsToday),
        ),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("$0.0000")).toBeVisible();
  },
};

/** Request in flight — `data` is undefined, so the chip shows the `?? 0` fallback. */
export const Loading: Story = {
  args: {},
  parameters: {
    msw: {
      handlers: [
        http.get(COSTS_TODAY_URL, async () => {
          await delay("infinite");
          return HttpResponse.json(today);
        }),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Today")).toBeVisible();
    await expect(canvas.getByText("$0.0000")).toBeVisible();
  },
};
