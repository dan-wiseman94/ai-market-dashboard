import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ThesesPage from "../pages/ThesesPage";
import { mockApi, renderWithProviders } from "./testUtils";

const OPEN_THESIS = {
  id: 1,
  title: "SPY hits 600",
  ticker: "SPY",
  direction: "bullish" as const,
  rationale: "Momentum",
  conviction: 4,
  entry_price: "550.00",
  target_price: "600.00",
  invalidation_price: null,
  horizon_days: 90,
  status: "open" as const,
  profile_id: null,
  thread_id: null,
  snapshot_id: null,
  review_thread_id: null,
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_note: "",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  postmortems: [],
};

const WIN_THESIS = {
  ...OPEN_THESIS,
  id: 2,
  title: "AAPL earnings pop",
  ticker: "AAPL",
  direction: "bullish" as const,
  status: "closed_win" as const,
  closed_at: "2026-05-20T00:00:00Z",
};

describe("ThesesPage", () => {
  it("shows loading skeleton while fetching", () => {
    // Never resolves — simulates loading state
    globalThis.fetch = (() => new Promise(() => {})) as typeof fetch;
    renderWithProviders(<ThesesPage />, {
      initialEntries: ["/theses"],
    });
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });

  it("shows empty state when there are no theses", async () => {
    mockApi({ "GET /api/theses/": [] });
    renderWithProviders(<ThesesPage />, { initialEntries: ["/theses"] });
    await waitFor(() =>
      expect(screen.getByText(/no theses yet/i)).toBeInTheDocument(),
    );
  });

  it("renders open and closed groups with correct status badges", async () => {
    mockApi({ "GET /api/theses/": [OPEN_THESIS, WIN_THESIS] });
    renderWithProviders(<ThesesPage />, { initialEntries: ["/theses"] });

    await waitFor(() =>
      expect(screen.getByText("SPY hits 600")).toBeInTheDocument(),
    );

    // Both thesis titles appear
    expect(screen.getByText("AAPL earnings pop")).toBeInTheDocument();

    // Section headings (h2 elements)
    const headings = screen.getAllByRole("heading", { level: 2 });
    const headingTexts = headings.map((h) => h.textContent);
    expect(headingTexts).toContain("Open");
    expect(headingTexts).toContain("Closed");

    // Status badges identified by testid
    expect(screen.getByTestId("status-badge-open")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge-closed_win")).toBeInTheDocument();
  });

  it("renders conviction stars", async () => {
    mockApi({ "GET /api/theses/": [OPEN_THESIS] });
    renderWithProviders(<ThesesPage />, { initialEntries: ["/theses"] });
    await waitFor(() =>
      expect(screen.getByText("SPY hits 600")).toBeInTheDocument(),
    );
    // Conviction 4 → ★★★★☆
    expect(screen.getByLabelText(/conviction 4/i)).toBeInTheDocument();
  });

  it("renders ticker and direction for each thesis", async () => {
    mockApi({ "GET /api/theses/": [OPEN_THESIS] });
    renderWithProviders(<ThesesPage />, { initialEntries: ["/theses"] });
    await waitFor(() =>
      expect(screen.getByText("SPY")).toBeInTheDocument(),
    );
    expect(screen.getByText(/bullish/i)).toBeInTheDocument();
  });

  it("shows open/closed summary counts", async () => {
    mockApi({ "GET /api/theses/": [OPEN_THESIS, WIN_THESIS] });
    renderWithProviders(<ThesesPage />, { initialEntries: ["/theses"] });
    await waitFor(() =>
      expect(screen.getByText(/1 open · 1 closed/i)).toBeInTheDocument(),
    );
  });
});
