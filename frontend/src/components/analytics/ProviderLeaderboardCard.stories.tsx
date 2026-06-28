import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse, delay } from "msw";
import type { LeaderboardRow } from "@/hooks/useAnalytics";
import { ProviderLeaderboardCard } from "./ProviderLeaderboardCard";

// useLeaderboard() stamps a fresh `start` ISO on every render, so we match on the
// path only — MSW ignores query params unless the matcher specifies them.
const LEADERBOARD_URL = "/api/analytics/leaderboard/";

const rows: LeaderboardRow[] = [
  {
    provider: "anthropic",
    model: "claude-opus-4-8",
    runs: 42,
    total_cost_usd: "1.873",
    avg_latency_ms: 4200,
    avg_forward_return_pct: 1.34,
    coverage_pct: 86,
  },
  {
    provider: "openai",
    model: "gpt-5",
    runs: 31,
    total_cost_usd: "0.945",
    avg_latency_ms: 3100,
    avg_forward_return_pct: -0.52,
    coverage_pct: 71,
  },
  {
    provider: "local",
    model: "llama-3.3-70b",
    runs: 12,
    total_cost_usd: "0",
    avg_latency_ms: 8800,
    avg_forward_return_pct: null,
    coverage_pct: 0,
  },
];

const meta = {
  title: "Content/ProviderLeaderboardCard",
  component: ProviderLeaderboardCard,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Analytics card ranking each (provider, model) over 30 days. Self-fetches `/api/analytics/leaderboard/` via react-query — these stories mock that endpoint with MSW to exercise the populated, empty, loading, and errored states.",
      },
    },
  },
} satisfies Meta<typeof ProviderLeaderboardCard>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A populated leaderboard: cost is dollar-formatted, a null forward return shows "—". */
export const Populated: Story = {
  parameters: {
    msw: { handlers: [http.get(LEADERBOARD_URL, () => HttpResponse.json({ rows }))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("claude-opus-4-8")).toBeVisible();
    await expect(canvas.getByText("gpt-5")).toBeVisible();
    // total_cost_usd "1.873" renders as "$1.87".
    await expect(canvas.getByText("$1.87")).toBeVisible();
    // The footer caption that explains the Fwd % / Cov columns.
    await expect(canvas.getByText(/share of runs with a real price bar/i)).toBeVisible();
  },
};

/** No runs in the window — the table renders with only its header row and the caption. */
export const Empty: Story = {
  parameters: {
    msw: { handlers: [http.get(LEADERBOARD_URL, () => HttpResponse.json({ rows: [] }))] },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/share of runs with a real price bar/i)).toBeVisible();
    // Header is present, but no model rows rendered.
    await expect(canvas.getByText("Model")).toBeVisible();
    await expect(canvas.queryByText("claude-opus-4-8")).toBeNull();
  },
};

/** Request in flight — the handler never resolves, so the "Loading…" line stays. */
export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(LEADERBOARD_URL, async () => {
          await delay("infinite");
          return HttpResponse.json({ rows: [] });
        }),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/loading/i)).toBeVisible();
  },
};

/** Server error — the failure surface (retries are off in the story QueryClient). */
export const Errored: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(LEADERBOARD_URL, () => HttpResponse.json({ message: "boom" }, { status: 500 })),
      ],
    },
  },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText(/boom/i)).toBeVisible();
  },
};
