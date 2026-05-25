import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { WatchlistSymbol } from "@/api/watchlists";
import WatchlistTable from "./WatchlistTable";

const symbols: WatchlistSymbol[] = [
  { id: 1, ticker: "AAPL", sort_order: 0 },
  { id: 2, ticker: "NVDA", sort_order: 1 },
  { id: 3, ticker: "MSFT", sort_order: 2 },
];

const quotes = {
  AAPL: { last: 198.5, bid: 198.4, ask: 198.6, volume: 51_200_000, high: 199.1, low: 196.8, pct_change: 1.24 },
  NVDA: { last: 590.2, bid: 590.0, ask: 590.5, volume: 38_900_000, high: 601.0, low: 585.3, pct_change: -1.85 },
  MSFT: { last: 421.7, bid: 421.6, ask: 421.9, volume: 18_400_000, high: 423.0, low: 419.2, pct_change: 0.42 },
};

const meta = {
  title: "Market/WatchlistTable",
  component: WatchlistTable,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    // Symbols arrive as props; quote cells fetch `/api/market/quotes/`, mocked here.
    msw: { handlers: [http.get("/api/market/quotes/", () => HttpResponse.json(quotes))] },
    docs: {
      description: {
        component:
          "Watchlist rows with live quote cells. Symbols come in as props; quotes are fetched (and mocked here) from `/api/market/quotes/`.",
      },
    },
  },
  args: { symbols },
  argTypes: {
    symbols: { control: "object", description: "Watchlist symbols to render." },
    onRemove: { description: "Optional remove handler; shows a Remove action per row." },
  },
} satisfies Meta<typeof WatchlistTable>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Quote cells fill in once the mocked `/api/market/quotes/` response resolves. */
export const WithQuotes: Story = {
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("590.20")).toBeVisible();
  },
};

/** With a remove handler wired, each row exposes a Remove action. */
export const Removable: Story = {
  args: { onRemove: fn() },
  play: async ({ canvas, userEvent, args }) => {
    const [first] = await canvas.findAllByRole("button", { name: /remove/i });
    await userEvent.click(first);
    await expect(args.onRemove).toHaveBeenCalledWith(1);
  },
};
