import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { CalendarMarketStatus } from "@/api/market";
import MarketStatusBadge from "./MarketStatusBadge";

const STATUS_URL = "/api/market/calendar-status/";

const market = (over: Partial<CalendarMarketStatus>): CalendarMarketStatus => ({
  is_open: false,
  phase: "closed",
  is_early_close: false,
  next_open: null,
  next_close: null,
  ...over,
});

const status = (markets: Record<string, CalendarMarketStatus>) =>
  http.get(STATUS_URL, () => HttpResponse.json({ markets }));

const meta = {
  title: "Market/MarketStatusBadge",
  component: MarketStatusBadge,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Nav badge that reads `/api/market/calendar-status/` and renders the authoritative session state — a single market shows Open / Extended Hours / Closed, multiple markets collapse to an `N/M open` count. Renders nothing when no markets are returned.",
      },
    },
  },
} satisfies Meta<typeof MarketStatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A single open market — emerald dot, "Open" label. */
export const Open: Story = {
  args: {},
  parameters: {
    msw: { handlers: [status({ us_equity: market({ is_open: true, phase: "open" }) })] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Open")).toBeVisible();
    await expect(canvas.getByTestId("market-status")).toBeVisible();
  },
};

/** Pre/post market hours map to the "Extended Hours" session. */
export const ExtendedHours: Story = {
  args: {},
  parameters: {
    msw: { handlers: [status({ us_equity: market({ is_open: false, phase: "premarket" }) })] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Extended Hours")).toBeVisible();
  },
};

/** Closed market — slate dot, "Closed" label. */
export const Closed: Story = {
  args: {},
  parameters: {
    msw: { handlers: [status({ us_equity: market({ is_open: false, phase: "closed" }) })] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Closed")).toBeVisible();
  },
};

/** Two markets collapse to an open-count summary. */
export const MultipleMarkets: Story = {
  args: {},
  parameters: {
    msw: {
      handlers: [
        status({
          us_equity: market({ is_open: true, phase: "open" }),
          lse: market({ is_open: false, phase: "closed" }),
        }),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("1/2 open")).toBeVisible();
  },
};

/** No markets returned — the badge renders nothing at all. */
export const NoMarkets: Story = {
  args: {},
  parameters: {
    msw: { handlers: [status({})] },
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByTestId("market-status")).toBeNull();
  },
};
