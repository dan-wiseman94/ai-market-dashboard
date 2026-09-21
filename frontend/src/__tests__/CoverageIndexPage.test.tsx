import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import CoverageIndexPage from "@/pages/CoverageIndexPage";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";

const ROWS = [
  {
    id: 1,
    ticker: "SPY",
    stance: "bull",
    conviction: 4,
    revision_count: 3,
    last_revised_at: "2026-06-01T00:00:00Z",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  },
  {
    id: 2,
    ticker: "NVDA",
    stance: "bear",
    conviction: 2,
    revision_count: 1,
    last_revised_at: "2026-05-20T00:00:00Z",
    created_at: "2026-05-02T00:00:00Z",
    updated_at: "2026-05-20T00:00:00Z",
  },
];

let api: FetchMock;

afterEach(() => api?.restore());

describe("CoverageIndexPage", () => {
  it("lists every covered ticker and links to its note", async () => {
    api = mockApi({ "GET /api/coverage/": ROWS });
    renderWithProviders(<CoverageIndexPage />);

    await waitFor(() => expect(screen.getByText("SPY")).toBeInTheDocument());
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    // Scope to the rows: "Bullish"/"Bearish" are also the stance filter's options.
    const spy = within(screen.getByTestId("coverage-row-SPY"));
    expect(spy.getByText("Bullish")).toBeInTheDocument();
    expect(spy.getByText("conviction 4/5")).toBeInTheDocument();
    expect(spy.getByText("3 revisions")).toBeInTheDocument();
    expect(within(screen.getByTestId("coverage-row-NVDA")).getByText("Bearish"))
      .toBeInTheDocument();
    expect(screen.getByRole("link", { name: /SPY/ })).toHaveAttribute(
      "href",
      "/coverage/SPY",
    );
  });

  it("filters by stance", async () => {
    api = mockApi({ "GET /api/coverage/": ROWS });
    renderWithProviders(<CoverageIndexPage />);

    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Stance"), "bull");

    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();
  });

  it("explains how the first note gets opened when nothing is covered", async () => {
    api = mockApi({ "GET /api/coverage/": [] });
    renderWithProviders(<CoverageIndexPage />);

    await waitFor(() =>
      expect(screen.getByText(/No tickers covered yet/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/observer fire opens the first house view/)).toBeInTheDocument();
  });
});
