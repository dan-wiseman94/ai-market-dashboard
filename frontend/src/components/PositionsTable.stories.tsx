import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse, delay } from "msw";
import type { Position } from "@/api/market";
import PositionsTable from "./PositionsTable";

const POSITIONS_URL = "/api/market/positions/";

const positions: Position[] = [
  { ticker: "AAPL", qty: 100, avg_cost: 182.4, mkt_value: 19_850, unrealized_pl: 1610, day_pl: 240 },
  { ticker: "NVDA", qty: 40, avg_cost: 640.1, mkt_value: 23_600, unrealized_pl: -1004, day_pl: -380 },
  { ticker: "SPY", qty: 50, avg_cost: 511.2, mkt_value: 26_500, unrealized_pl: 940, day_pl: 60 },
];

const meta = {
  title: "Market/PositionsTable",
  component: PositionsTable,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "The open-positions book. Fetches `/api/market/positions/` via react-query — these stories mock that endpoint with MSW to exercise the loading, error, empty, and populated states.",
      },
    },
  },
} satisfies Meta<typeof PositionsTable>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Populated book with gain/loss tones and a totals row. */
export const Populated: Story = {
  parameters: {
    msw: { handlers: [http.get(POSITIONS_URL, () => HttpResponse.json(positions))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("NVDA")).toBeVisible();
    await expect(canvas.getByText("Book totals")).toBeVisible();
  },
};

/** No open positions — the "Flat." empty state. */
export const Empty: Story = {
  parameters: {
    msw: { handlers: [http.get(POSITIONS_URL, () => HttpResponse.json([]))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("Flat.")).toBeVisible();
  },
};

/** Request in flight — the handler never resolves, so the skeleton rows stay. */
export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(POSITIONS_URL, async () => {
          await delay("infinite");
          return HttpResponse.json([]);
        }),
      ],
    },
  },
  play: async ({ canvas }) => {
    const rows = await canvas.findAllByTestId("skeleton-row");
    await expect(rows[0]).toBeVisible();
  },
};

/** Server error — the failure surface (retries are off in the story QueryClient). */
export const Errored: Story = {
  parameters: {
    msw: {
      handlers: [http.get(POSITIONS_URL, () => HttpResponse.json({ message: "boom" }, { status: 500 }))],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/could not load positions/i)).toBeVisible();
  },
};
