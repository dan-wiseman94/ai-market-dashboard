import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { Firing } from "@/api/triggers";
import FiringsTable from "@/components/triggers/FiringsTable";
import { mockApi, renderWithProviders } from "../testUtils";

const ROUTE = "GET /api/triggers/5/firings/";

// fired: has a thread, not cost-capped. matched_values includes a null entry and a
// "_prior:" snapshot of the previous value — both must be filtered out of the cell.
const FIRED: Firing = {
  id: 1,
  trigger_id: 5,
  trigger_name: "SPY breakout",
  fired_at: "2026-04-18T14:42:00Z",
  matched_values: { "price:SPY": 551.2, vix: null, "_prior:price:SPY": 540 },
  snapshot_id: 9,
  thread_id: 7,
  cost_capped: false,
};

// cost-capped: no thread, both refs null.
const CAPPED: Firing = {
  id: 2,
  trigger_id: 5,
  trigger_name: "NVDA drop",
  fired_at: "2026-04-18T14:31:00Z",
  matched_values: { "pct_change:NVDA": -0.024 },
  snapshot_id: null,
  thread_id: null,
  cost_capped: true,
};

// error: not cost-capped but produced no thread.
const ERRORED: Firing = {
  id: 3,
  trigger_id: 5,
  trigger_name: "QQQ check",
  fired_at: "2026-04-18T14:20:00Z",
  matched_values: { "price:QQQ": 480 },
  snapshot_id: 10,
  thread_id: null,
  cost_capped: false,
};

function page(rows: Firing[]) {
  return { results: rows, count: rows.length, page: 1, size: 20 };
}

describe("FiringsTable", () => {
  it("shows a loading placeholder before data resolves", () => {
    mockApi({ [ROUTE]: page([]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an empty state when there are no firings", async () => {
    mockApi({ [ROUTE]: page([]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    await waitFor(() =>
      expect(screen.getByText("No firings yet.")).toBeInTheDocument(),
    );
  });

  it("renders matched values, filtering nulls and _prior: keys, and rounding numbers", async () => {
    mockApi({ [ROUTE]: page([FIRED]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    const cell = await screen.findByText(/price:SPY=551\.20/);
    // The null `vix` entry and the `_prior:` key must not appear.
    expect(cell.textContent).toBe("price:SPY=551.20");
  });

  it("links snapshot and thread ids to their detail routes", async () => {
    mockApi({ [ROUTE]: page([FIRED]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    const snap = await screen.findByRole("link", { name: "#9" });
    const thread = screen.getByRole("link", { name: "#7" });
    expect(snap).toHaveAttribute("href", "/snapshots/9");
    expect(thread).toHaveAttribute("href", "/threads/7");
  });

  it("shows a 'fired' badge for a successful, non-capped firing", async () => {
    mockApi({ [ROUTE]: page([FIRED]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    expect(await screen.findByText("fired")).toBeInTheDocument();
  });

  it("shows a 'cost-capped' badge and em-dashes for missing refs", async () => {
    mockApi({ [ROUTE]: page([CAPPED]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    expect(await screen.findByText("cost-capped")).toBeInTheDocument();
    // Both snapshot and thread are null → two em-dash placeholders, no links.
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows an 'error' badge when there is no thread and it was not capped", async () => {
    mockApi({ [ROUTE]: page([ERRORED]) });
    renderWithProviders(<FiringsTable triggerId={5} />);
    expect(await screen.findByText("error")).toBeInTheDocument();
  });
});
