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

describe("RecallPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows empty state before any search", () => {
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });
    expect(screen.getByTestId("recall-query-input")).toBeInTheDocument();
    // No results shown yet
    expect(screen.queryByTestId("mode-badge")).not.toBeInTheDocument();
  });

  it("renders snippet, kind badge, and link after a search", async () => {
    mockApi({
      "GET /api/recall/": RECALL_RESULT,
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

    // Link renders
    expect(screen.getByText("→ /theses/42")).toBeInTheDocument();
  });

  it("shows the mode badge after a search", async () => {
    mockApi({
      "GET /api/recall/": RECALL_RESULT,
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
    });
    renderWithProviders(<RecallPage />, { initialEntries: ["/recall"] });

    const input = screen.getByTestId("recall-query-input");
    fireEvent.change(input, { target: { value: "xyznothing" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() =>
      expect(screen.getByText(/no results found/i)).toBeInTheDocument(),
    );
  });
});
