import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RecentTriggersCard from "../components/RecentTriggersCard";

const FIRINGS = [
  {
    id: 1, trigger_id: 10, trigger_name: "SPY breakout",
    fired_at: "2026-04-18T14:42:00Z",
    matched_values: { "price:SPY": 551.2 },
    snapshot_id: 9, thread_id: 7, cost_capped: false,
  },
  {
    id: 2, trigger_id: 11, trigger_name: "NVDA -2%",
    fired_at: "2026-04-18T14:31:00Z",
    matched_values: { "pct_change:NVDA:5m": -0.024 },
    snapshot_id: 10, thread_id: null, cost_capped: true,
  },
];

function mount(rows: unknown[]) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(rows) }),
  ) as never;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><RecentTriggersCard /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RecentTriggersCard", () => {
  it("renders rows with trigger name + matched values", async () => {
    mount(FIRINGS);
    await waitFor(() => expect(screen.getByText(/SPY breakout/)).toBeInTheDocument());
    expect(screen.getByText(/NVDA -2%/)).toBeInTheDocument();
    expect(screen.getByText(/551\.20/)).toBeInTheDocument();
  });

  it("renders cost-capped badge when thread is null", async () => {
    mount(FIRINGS);
    await waitFor(() => expect(screen.getByText(/cost-capped/i)).toBeInTheDocument());
  });

  it("returns nothing when there are no firings", async () => {
    const { container } = mount([]);
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
