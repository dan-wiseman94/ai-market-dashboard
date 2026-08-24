import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse, delay } from "msw";
import type { Firing } from "@/api/triggers";
import FiringsTable from "./FiringsTable";

const TRIGGER_ID = 42;
// fetchFirings(triggerId) hits /api/triggers/<id>/firings/?page=&page_size= — the
// path param is matched here; MSW ignores the query string by default.
const FIRINGS_URL = "/api/triggers/:id/firings/";

const firings: Firing[] = [
  {
    id: 1,
    trigger_id: TRIGGER_ID,
    trigger_name: "SPY breakout",
    fired_at: "2026-06-20T14:31:00Z",
    // `_prior:`-prefixed and null entries are filtered out of the cell text.
    matched_values: { price: 152.34, "_prior:price": 150.1 },
    snapshot_id: 12,
    thread_id: 7,
    cost_capped: false,
  },
  {
    id: 2,
    trigger_id: TRIGGER_ID,
    trigger_name: "SPY breakout",
    fired_at: "2026-06-21T09:45:00Z",
    matched_values: { pct_change: -3.5 },
    snapshot_id: 13,
    thread_id: null,
    cost_capped: true,
  },
  {
    id: 3,
    trigger_id: TRIGGER_ID,
    trigger_name: "SPY breakout",
    fired_at: "2026-06-22T16:02:00Z",
    matched_values: { volume_z: 2.1 },
    snapshot_id: null,
    thread_id: null,
    cost_capped: false,
  },
];

// DRF PageNumberPagination envelope.
const page = (results: Firing[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

const meta = {
  title: "Observer/FiringsTable",
  component: FiringsTable,
  tags: ["ai-generated"],
  args: { triggerId: TRIGGER_ID },
  argTypes: {
    triggerId: { control: "number", description: "Trigger whose firings to fetch." },
  },
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Per-trigger firing log. Fetches `/api/triggers/<id>/firings/` via react-query — these stories mock that endpoint with MSW to exercise the populated, empty, and loading states. Each row shows matched values (dropping `_prior:` baselines), snapshot/thread ref links, and a status badge (fired / cost-capped / error).",
      },
    },
  },
} satisfies Meta<typeof FiringsTable>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A fired, a cost-capped, and an errored row — the three status badges. */
export const Populated: Story = {
  parameters: {
    msw: { handlers: [http.get(FIRINGS_URL, () => HttpResponse.json(page(firings)))] },
  },
  play: async ({ canvas }) => {
    // Number values render via toFixed(2); the `_prior:price` baseline is hidden.
    await expect(await canvas.findByText("price=152.34")).toBeVisible();
    await expect(canvas.getByText("Matched values")).toBeVisible();
    await expect(canvas.getByText("fired")).toBeVisible();
    await expect(canvas.getByText("cost-capped")).toBeVisible();
    await expect(canvas.getByText("error")).toBeVisible();
    // snapshot_id 12 resolves to a "#12" ref link.
    await expect(canvas.getByRole("link", { name: "#12" })).toBeVisible();
  },
};

/** No firings yet — the empty line. */
export const Empty: Story = {
  parameters: {
    msw: { handlers: [http.get(FIRINGS_URL, () => HttpResponse.json(page([])))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/no firings yet/i)).toBeVisible();
  },
};

/** Request in flight — the handler never resolves, so the loading line stays. */
export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(FIRINGS_URL, async () => {
          await delay("infinite");
          return HttpResponse.json(page([]));
        }),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/loading/i)).toBeVisible();
  },
};
