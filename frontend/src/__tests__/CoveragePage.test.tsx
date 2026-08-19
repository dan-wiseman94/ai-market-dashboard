import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CoveragePage from "../pages/CoveragePage";

const NOTE = {
  id: 1,
  ticker: "SPY",
  stance: "bull",
  conviction: 4,
  bull_case: "trend intact above 520",
  bear_case: "CPI risk into the print",
  key_levels: { support: 520, resistance: 535 },
  watching_for: "the 10:00 breadth reading",
  created_at: "2026-05-30T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  revisions: [
    {
      id: 2,
      prior: { stance: "neutral", conviction: 2 },
      new: { stance: "bull", conviction: 4 },
      reason: "broke out of the range",
      source_snapshot_id: 9,
      created_at: "2026-06-01T00:00:00Z",
    },
    {
      id: 1,
      prior: {},
      new: { stance: "neutral", conviction: 2 },
      reason: "established coverage",
      source_snapshot_id: 8,
      created_at: "2026-05-30T00:00:00Z",
    },
  ],
};

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderAt(path: string, payload: unknown, ok = true, status = 200) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok, status, json: () => Promise.resolve(payload) }),
  ) as never;
  render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/coverage/:ticker" element={<CoveragePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CoveragePage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the house view and its revision history", async () => {
    renderAt("/coverage/SPY", NOTE);
    // Wait on note-derived content — the <h1> shows the URL ticker before the
    // query resolves, so waiting on "SPY" alone wouldn't prove the note loaded.
    await waitFor(() =>
      expect(screen.getByText(/trend intact above 520/)).toBeInTheDocument(),
    );
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/CPI risk into the print/)).toBeInTheDocument();
    expect(screen.getByText(/broke out of the range/)).toBeInTheDocument();
    expect(screen.getByText(/established coverage/)).toBeInTheDocument();
  });

  it("shows an empty state when the ticker is not yet covered", async () => {
    renderAt("/coverage/NEW", { message: "not found" }, false, 404);
    await waitFor(() =>
      expect(screen.getByText(/No coverage yet/i)).toBeInTheDocument(),
    );
  });
});
