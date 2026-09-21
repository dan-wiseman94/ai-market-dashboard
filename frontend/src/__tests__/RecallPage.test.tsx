import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import RecallPage from "../pages/RecallPage";
import { mockApi, renderWithProviders } from "./testUtils";

const RECALL_RESULT = {
  results: [
    {
      kind: "thesis",
      object_id: 42,
      snippet: "NVDA bullish into earnings — AI demand accelerating",
      link: "/theses/42",
      source_created_at: "2026-05-01T00:00:00Z",
      tickers: ["NVDA"],
    },
  ],
  mode: "semantic" as const,
};

const RECALL_STATUS = {
  counts: {
    message: 12,
    snapshot: 4,
    thesis: 7,
    journal: 0,
    observation: 3,
    postmortem: 1,
    total: 27,
  },
  mode: "semantic" as const,
};

describe("RecallPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows empty state before any search", () => {
    mockApi({
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });
    expect(screen.getByTestId("recall-query-input")).toBeInTheDocument();
    expect(screen.queryByTestId("mode-badge")).not.toBeInTheDocument();
  });

  it("renders snippet, kind badge, and link after a search", async () => {
    mockApi({
      "GET /api/recall/": RECALL_RESULT,
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "NVDA earnings" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() =>
      expect(screen.getByText(/NVDA bullish into earnings/i)).toBeInTheDocument(),
    );

    // Kind badge renders (appears in section heading + inline badge — ensure at least one is present)
    expect(screen.getAllByText("thesis").length).toBeGreaterThan(0);

    expect(screen.getByText("→ /theses/42")).toBeInTheDocument();
  });

  it("shows the mode badge after a search", async () => {
    mockApi({
      "GET /api/recall/": RECALL_RESULT,
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "NVDA earnings" } });
    fireEvent.submit(input.closest("form")!);

    const badge = await screen.findByTestId("mode-badge");
    expect(badge).toHaveTextContent("semantic");
  });

  it("shows the keyword mode badge when mode is keyword", async () => {
    mockApi({
      "GET /api/recall/": { ...RECALL_RESULT, mode: "keyword" },
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "earnings" } });
    fireEvent.submit(input.closest("form")!);

    const badge = await screen.findByTestId("mode-badge");
    expect(badge).toHaveTextContent("keyword");
  });

  it("shows empty state when no results found", async () => {
    mockApi({
      "GET /api/recall/": { results: [], mode: "keyword" },
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "xyznothing" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() =>
      expect(screen.getByText(/no results found/i)).toBeInTheDocument(),
    );
  });

  it("renders the index-health readout with mode and per-kind counts", async () => {
    mockApi({
      "GET /api/recall/status/": RECALL_STATUS,
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const readout = await screen.findByTestId("recall-status");
    expect(screen.getByTestId("recall-status-mode")).toHaveTextContent("semantic");
    expect(readout).toHaveTextContent("27 indexed");
    expect(readout).toHaveTextContent("message 12");
    expect(readout).toHaveTextContent("postmortem 1");
    // The loading skeleton is gone once the readout renders.
    expect(screen.queryByTestId("skeleton-recall-status")).not.toBeInTheDocument();
  });

  it("explains what the backfill does and what it costs", async () => {
    mockApi({ "GET /api/recall/status/": RECALL_STATUS });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const button = await screen.findByRole("button", { name: /backfill index/i });
    // The explanation is wired to the control, not just floating nearby.
    const help = document.getElementById(button.getAttribute("aria-describedby") ?? "");
    expect(help).toHaveTextContent(/re-embeds every document still pending semantic indexing/i);
    expect(help).toHaveTextContent(/no provider spend/i);
  });

  it("reports a queued backfill as queued, not finished, and refetches the counts", async () => {
    const fetchMock = mockApi({
      "GET /api/recall/status/": RECALL_STATUS,
      "POST /api/recall/backfill/": { task_id: "bf-9", status: "queued" },
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    await screen.findByTestId("recall-status");
    const before = fetchMock.calls.filter((c) => c.url.includes("/api/recall/status/")).length;

    fireEvent.click(screen.getByRole("button", { name: /backfill index/i }));

    const banner = await screen.findByTestId("recall-backfill-queued");
    expect(banner).toHaveTextContent("bf-9");
    expect(banner).toHaveTextContent(/queued is not finished/i);

    // Queuing invalidates the status query, so the counts re-read.
    await waitFor(() =>
      expect(
        fetchMock.calls.filter((c) => c.url.includes("/api/recall/status/")).length,
      ).toBeGreaterThan(before),
    );
  });

  it("surfaces a failed backfill instead of claiming it was queued", async () => {
    mockApi({
      "GET /api/recall/status/": RECALL_STATUS,
      "POST /api/recall/backfill/": { status: 500, message: "worker unreachable" },
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    fireEvent.click(await screen.findByRole("button", { name: /backfill index/i }));

    expect(await screen.findByText(/worker unreachable/i)).toBeInTheDocument();
    expect(screen.queryByTestId("recall-backfill-queued")).not.toBeInTheDocument();
  });

  it("omits the readout when the status endpoint errors, without breaking search", async () => {
    mockApi({
      "GET /api/recall/": RECALL_RESULT,
      "GET /api/recall/status/": { status: 500 },
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    // Skeleton resolves to nothing — the readout is omitted, not an error UI.
    await waitFor(() =>
      expect(screen.queryByTestId("skeleton-recall-status")).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId("recall-status")).not.toBeInTheDocument();

    // Search still works.
    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "NVDA earnings" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() =>
      expect(screen.getByText(/NVDA bullish into earnings/i)).toBeInTheDocument(),
    );
  });
});
