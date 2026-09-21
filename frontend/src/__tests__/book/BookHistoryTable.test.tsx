import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BookSnapshotTrend } from "@/api/book";
import BookHistoryTable from "@/components/book/BookHistoryTable";
import { mockApi, renderWithProviders, type FetchMock } from "../testUtils";

function trend(over: Partial<BookSnapshotTrend> = {}): BookSnapshotTrend {
  return {
    id: 1, created_at: "2026-09-01T00:00:00Z", as_of_date: "2026-09-01",
    hhi: 0.42, top_n_share: 0.7, total_abs: 10, net_long: 8, net_short: -2,
    gross_dollar: 120000, net_dollar: 80000, diversified_var_usd: 2400,
    undiversified_var_usd: 3100, beta_adjusted_net_exposure_usd: 96000,
    regime: "risk_off", alignment: "misaligned",
    position_count: 4, cluster_count: 1, near_invalidation_count: 0,
    ...over,
  };
}

let api: FetchMock;
afterEach(() => api?.restore());

describe("BookHistoryTable", () => {
  it("renders one row per stored reading", async () => {
    api = mockApi({ "GET /api/book/": [trend(), trend({ id: 2, as_of_date: "2026-08-31" })] });
    renderWithProviders(<BookHistoryTable />);
    expect(await screen.findByText("2026-09-01")).toBeInTheDocument();
    expect(screen.getByText("2026-08-31")).toBeInTheDocument();
    expect(screen.getAllByText("0.42").length).toBe(2);
    expect(screen.getAllByText("70%").length).toBe(2);
  });

  it("shows a gap, not a zero, for a metric the day never had", async () => {
    api = mockApi({
      "GET /api/book/": [trend({ diversified_var_usd: null, hhi: null, alignment: null })],
    });
    renderWithProviders(<BookHistoryTable />);
    await screen.findByText("2026-09-01");
    expect(screen.getAllByText("—").length).toBe(3);
    expect(screen.queryByText("$0")).not.toBeInTheDocument();
  });

  it("empty state before a second reading exists", async () => {
    api = mockApi({ "GET /api/book/": [] });
    renderWithProviders(<BookHistoryTable />);
    expect(await screen.findByText(/No earlier readings/i)).toBeInTheDocument();
  });

  it("refetches with the chosen window", async () => {
    api = mockApi({ "GET /api/book/": [trend()] });
    renderWithProviders(<BookHistoryTable />);
    await screen.findByText("2026-09-01");
    expect(api.calls[0].url).toContain("limit=30");
    fireEvent.change(screen.getByLabelText(/window/i), { target: { value: "365" } });
    await waitFor(() => expect(api.calls.some((c) => c.url.includes("limit=365"))).toBe(true));
  });
});
