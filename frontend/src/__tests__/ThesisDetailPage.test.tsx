import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import ThesisDetailPage from "../pages/ThesisDetailPage";
import { mockApi, renderWithProviders } from "./testUtils";
import type { PostMortem } from "@/api/thesis";

const BASE_THESIS = {
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
  guard_enabled: false,
  guard_trigger_id: null,
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_note: "",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  postmortems: [] as PostMortem[],
};

const THESIS = BASE_THESIS;

const CLOSED_THESIS = {
  ...THESIS,
  id: 2,
  status: "closed_win" as const,
  closed_at: "2026-05-20T00:00:00Z",
  close_note: "Worked perfectly",
};

const DONE_PM: PostMortem = {
  id: 10,
  horizon_days: 7,
  due_at: "2026-05-08T00:00:00Z",
  status: "done",
  forward_return_pct: 3.2,
  verdict: "correct",
  report: {
    summary: "Thesis played out as expected with strong momentum.",
    what_worked: ["Trend identification"],
    what_missed: ["Underestimated volatility"],
    lessons: ["Size appropriately given macro backdrop"],
    would_repeat: true,
    narrative_verdict: "correct",
  },
  message_id: 99,
  created_at: "2026-05-01T00:00:00Z",
  completed_at: "2026-05-08T12:00:00Z",
};

const SCHEDULED_PM: PostMortem = {
  id: 11,
  horizon_days: 30,
  due_at: "2026-05-31T00:00:00Z",
  status: "scheduled",
  forward_return_pct: null,
  verdict: "",
  report: {},
  message_id: null,
  created_at: "2026-05-01T00:00:00Z",
  completed_at: null,
};

const THESIS_WITH_PMS = {
  ...THESIS,
  postmortems: [DONE_PM, SCHEDULED_PM],
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

  it("shows empty post-mortems state when postmortems is empty", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByText("SPY hits 600")).toBeInTheDocument(),
    );
    expect(screen.getByText("No post-mortems yet")).toBeInTheDocument();
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

  // --- Post-mortem section tests ---

  it("renders the Run now button", async () => {
    mockApi({ "GET /api/theses/1/": THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() =>
      expect(screen.getByTestId("run-postmortem-btn")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("run-postmortem-btn")).toHaveTextContent("Run now");
  });

  it("renders the done post-mortem card with verdict badge, forward return, summary and lessons", async () => {
    mockApi({ "GET /api/theses/1/": THESIS_WITH_PMS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("pm-card-7")).toBeInTheDocument(),
    );

    // Verdict badge present
    expect(screen.getByTestId("verdict-badge-correct")).toBeInTheDocument();
    expect(screen.getByText("Correct")).toBeInTheDocument();

    // Forward return formatted as signed percentage
    expect(screen.getByTestId("pm-return-7")).toHaveTextContent("+3.2%");

    // Summary text
    expect(
      screen.getByText("Thesis played out as expected with strong momentum."),
    ).toBeInTheDocument();

    // Lesson
    expect(
      screen.getByText("Size appropriately given macro backdrop"),
    ).toBeInTheDocument();
  });

  it("renders the scheduled post-mortem card with 'Scheduled for' state (no verdict/return)", async () => {
    mockApi({ "GET /api/theses/1/": THESIS_WITH_PMS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("pm-card-30")).toBeInTheDocument(),
    );

    // Shows scheduled state text
    expect(screen.getByText(/Scheduled for/)).toBeInTheDocument();

    // No verdict badge for the scheduled PM
    expect(screen.queryByTestId("verdict-badge-empty")).not.toBeInTheDocument();

    // No return shown for scheduled PM
    expect(screen.queryByTestId("pm-return-30")).not.toBeInTheDocument();
  });

  it("sorts post-mortem cards by horizon_days ascending", async () => {
    // Provide PMs in reverse order — 30-day first, 7-day second
    const REVERSED = {
      ...THESIS_WITH_PMS,
      postmortems: [SCHEDULED_PM, DONE_PM],
    };
    mockApi({ "GET /api/theses/1/": REVERSED });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("pm-card-7")).toBeInTheDocument(),
    );

    const cards = screen
      .getAllByTestId(/^pm-card-/)
      .map((el) => el.getAttribute("data-testid"));
    expect(cards).toEqual(["pm-card-7", "pm-card-30"]);
  });

  it("clicking Run now POSTs to /api/theses/{id}/run-postmortem/", async () => {
    const { calls } = mockApi({
      "GET /api/theses/1/": THESIS,
      "POST /api/theses/1/run-postmortem/": { postmortem_id: 42 },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("run-postmortem-btn")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("run-postmortem-btn"));

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/run-postmortem/") && c.method === "POST")).toBe(
        true,
      ),
    );
  });

  it("shows success toast after clicking Run now", async () => {
    mockApi({
      "GET /api/theses/1/": THESIS,
      "POST /api/theses/1/run-postmortem/": { postmortem_id: 42 },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("run-postmortem-btn")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("run-postmortem-btn"));

    await waitFor(() =>
      expect(screen.getByText("Post-mortem queued.")).toBeInTheDocument(),
    );
  });

  it("disables the Run now button while mutation is pending", async () => {
    let resolveFetch!: (value: unknown) => void;
    const pendingPromise = new Promise((res) => { resolveFetch = res; });

    mockApi({
      "GET /api/theses/1/": THESIS,
      "POST /api/theses/1/run-postmortem/": () => {
        // Keep the promise pending until we resolve it
        return pendingPromise as Promise<unknown>;
      },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("run-postmortem-btn")).toBeInTheDocument(),
    );

    const btn = screen.getByTestId("run-postmortem-btn");
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);

    await waitFor(() =>
      expect(screen.getByTestId("run-postmortem-btn")).toBeDisabled(),
    );

    // Resolve so we don't leave dangling promises
    resolveFetch({ postmortem_id: 99 });
  });

  it("renders 'Analysis failed.' for a failed PM with empty report", async () => {
    const FAILED_PM: PostMortem = {
      id: 12,
      horizon_days: 14,
      due_at: "2026-05-15T00:00:00Z",
      status: "failed",
      forward_return_pct: null,
      verdict: "",
      report: {},
      message_id: null,
      created_at: "2026-05-01T00:00:00Z",
      completed_at: null,
    };
    mockApi({
      "GET /api/theses/1/": { ...THESIS, postmortems: [FAILED_PM] },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("pm-card-14")).toBeInTheDocument(),
    );

    expect(screen.getByText("Analysis failed.")).toBeInTheDocument();
  });

  it("renders 'Analysis in progress…' for a running PM with empty report", async () => {
    const RUNNING_PM: PostMortem = {
      id: 13,
      horizon_days: 21,
      due_at: "2026-05-22T00:00:00Z",
      status: "running",
      forward_return_pct: null,
      verdict: "",
      report: {},
      message_id: null,
      created_at: "2026-05-01T00:00:00Z",
      completed_at: null,
    };
    mockApi({
      "GET /api/theses/1/": { ...THESIS, postmortems: [RUNNING_PM] },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByTestId("pm-card-21")).toBeInTheDocument(),
    );

    expect(screen.getByText("Analysis in progress…")).toBeInTheDocument();
  });
});
