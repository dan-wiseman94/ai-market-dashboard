import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { TrackRecord } from "@/hooks/useAnalytics";
import { TrackRecordHint } from "./TrackRecordHint";

const TRACK_RECORD_URL = "/api/analytics/track-record/";

type TrackRecordResponse = {
  ticker: string;
  available: boolean;
  record: TrackRecord | null;
};

const withSlice: TrackRecord = {
  ticker: "AAPL",
  closed_n: 12,
  counts: { win: 8, loss: 4, scratch: 0, invalidated: 0 },
  hit_rate: 0.667,
  last: { direction: "bullish", conviction: 4, status: "win" },
  slice: { direction: "bullish", conviction: 4, correct: 3, n: 4, hit_rate: 0.75 },
};

const minimal: TrackRecord = {
  ticker: "NVDA",
  closed_n: 5,
  counts: { win: 3, loss: 2, scratch: 0, invalidated: 0 },
  hit_rate: null,
  last: null,
  slice: null,
};

const ok = (record: TrackRecord): TrackRecordResponse => ({
  ticker: record.ticker,
  available: true,
  record,
});

const meta = {
  title: "Content/TrackRecordHint",
  component: TrackRecordHint,
  tags: ["ai-generated"],
  argTypes: {
    ticker: { control: "text", description: "Symbol whose closed-thesis record to surface." },
    direction: { control: "text", description: "Optional direction to narrow the conviction slice." },
    conviction: { control: { type: "number" }, description: "Optional conviction level for the slice." },
  },
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Inline hint summarizing the trader's closed-thesis track record for a ticker. Fetches `/api/analytics/track-record/` via react-query and renders nothing unless the response is available with a record.",
      },
    },
  },
} satisfies Meta<typeof TrackRecordHint>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Full record including the conviction/direction slice line. */
export const Default: Story = {
  args: { ticker: "AAPL", direction: "bullish", conviction: 4 },
  parameters: {
    msw: { handlers: [http.get(TRACK_RECORD_URL, () => HttpResponse.json(ok(withSlice)))] },
  },
  play: async ({ canvas }) => {
    const hint = await canvas.findByTestId("track-record-hint");
    await expect(hint).toBeVisible();
    await expect(canvas.getByText("Your AAPL track record:")).toBeVisible();
    await expect(hint).toHaveTextContent("12 closed");
    await expect(hint).toHaveTextContent("8W / 4L");
    await expect(hint).toHaveTextContent("(67%)");
    await expect(hint).toHaveTextContent("Conviction-4 bullish: 3/4 correct");
  },
};

/** Record with no hit rate and no slice — the bare win/loss line. */
export const WithoutSlice: Story = {
  args: { ticker: "NVDA" },
  parameters: {
    msw: { handlers: [http.get(TRACK_RECORD_URL, () => HttpResponse.json(ok(minimal)))] },
  },
  play: async ({ canvas }) => {
    const hint = await canvas.findByTestId("track-record-hint");
    await expect(hint).toHaveTextContent("5 closed");
    await expect(hint).toHaveTextContent("3W / 2L");
    await expect(hint.textContent ?? "").not.toContain("%");
    await expect(hint.textContent ?? "").not.toContain("Conviction-");
  },
};

/** No usable history — the API reports unavailable, so the component renders nothing. */
export const Unavailable: Story = {
  args: { ticker: "ZZZZ" },
  parameters: {
    msw: {
      handlers: [
        http.get(TRACK_RECORD_URL, () =>
          HttpResponse.json({ ticker: "ZZZZ", available: false, record: null }),
        ),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByTestId("track-record-hint")).toBeNull();
  },
};
