import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import ThesisDetailPage from "../pages/ThesisDetailPage";
import { mockApi, renderWithProviders } from "./testUtils";

const THESIS = {
  id: 1,
  title: "SPY hits 600",
  ticker: "SPY",
  direction: "bullish" as const,
  rationale: "Strong momentum behind the index",
  conviction: 3,
  entry_price: "550.00",
  target_price: "600.00",
  invalidation_price: "520.00",
  horizon_days: 90,
  status: "open" as const,
  profile_id: null,
  thread_id: 42,
  snapshot_id: null,
  review_thread_id: null,
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_note: "",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const CLOSED_THESIS = {
  ...THESIS,
  id: 2,
  status: "closed_win" as const,
  closed_at: "2026-05-20T00:00:00Z",
  close_note: "Worked perfectly",
};

describe("ThesisDetailPage", () => {
  it("renders thesis fields: title, ticker, direction, rationale, prices", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByText("SPY hits 600")).toBeInTheDocument(),
    );
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/bullish/i)).toBeInTheDocument();
    expect(screen.getByText(/strong momentum behind the index/i)).toBeInTheDocument();
    expect(screen.getByText("$550.00")).toBeInTheDocument();
    expect(screen.getByText("$600.00")).toBeInTheDocument();
    expect(screen.getByText("$520.00")).toBeInTheDocument();
    expect(screen.getByText("90 days")).toBeInTheDocument();
  });

  it("shows Open status badge for open thesis", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText("Open")).toBeInTheDocument(),
    );
  });

  it("shows Win status badge for closed_win thesis", async () => {
    mockApi({ "GET /api/theses/2/": CLOSED_THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/2"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText("Win")).toBeInTheDocument(),
    );
    expect(screen.getByText("Worked perfectly")).toBeInTheDocument();
  });

  it("renders the close control for an open thesis", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByTestId("open-close-form-btn")).toBeInTheDocument(),
    );
  });

  it("does NOT render the close button for a closed thesis", async () => {
    mockApi({ "GET /api/theses/2/": CLOSED_THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/2"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText("Win")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("open-close-form-btn")).not.toBeInTheDocument();
  });

  it("shows close form when 'Close thesis' button is clicked", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByTestId("open-close-form-btn")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("open-close-form-btn"));
    expect(screen.getByTestId("close-thesis-form")).toBeInTheDocument();
    // Outcome select is visible
    expect(screen.getByLabelText("Outcome")).toBeInTheDocument();
  });

  it("shows the post-mortem placeholder section", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText("SPY hits 600")).toBeInTheDocument(),
    );
    expect(screen.getByText("Post-mortems appear here")).toBeInTheDocument();
  });

  it("shows thread link with correct href when thread_id is set", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText(/Thread #42/)).toBeInTheDocument(),
    );
    const link = screen.getByText(/Thread #42/).closest("a");
    expect(link).toHaveAttribute("href", "/threads/42");
  });

  it("renders snapshot as plain text (not a link) when only snapshot_id is set", async () => {
    const SNAPSHOT_ONLY = {
      ...THESIS,
      thread_id: null,
      snapshot_id: 99,
    };
    mockApi({ "GET /api/theses/1/": SNAPSHOT_ONLY });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText(/Snapshot #99/)).toBeInTheDocument(),
    );
    // Must not be rendered inside an <a> element
    const el = screen.getByText(/Snapshot #99/);
    expect(el.closest("a")).toBeNull();
  });
});
