import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Briefing } from "@/api/briefing";
import BriefingHistoryList from "@/components/briefing/BriefingHistoryList";
import { mockApi, renderWithProviders, type FetchMock } from "../testUtils";

const EMPTY_DATA = {
  theses: [], events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x",
};

function run(id: number, day: string, status = "ready"): Briefing {
  return {
    id, created_at: `${day}T12:00:00Z`, status, scheduled_date: day,
    data: EMPTY_DATA, snapshot: null, synthesis_text: `s${id}`, synthesis_status: "done",
  };
}

let api: FetchMock;
afterEach(() => api?.restore());

describe("BriefingHistoryList", () => {
  it("lists past briefings newest first", async () => {
    api = mockApi({
      "GET /api/briefings/": { count: 2, next: null, previous: null,
        results: [run(2, "2026-09-02"), run(1, "2026-09-01")] },
    });
    renderWithProviders(<BriefingHistoryList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByText("2026-09-02")).toBeInTheDocument();
    expect(screen.getByText("2026-09-01")).toBeInTheDocument();
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
  });

  it("empty state when nothing has ever run", async () => {
    api = mockApi({
      "GET /api/briefings/": { count: 0, next: null, previous: null, results: [] },
    });
    renderWithProviders(<BriefingHistoryList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByText(/No past briefings/i)).toBeInTheDocument();
  });

  it("hands the whole row up on drill-in, and null when unselected", async () => {
    api = mockApi({
      "GET /api/briefings/": { count: 1, next: null, previous: null, results: [run(7, "2026-09-05")] },
    });
    const onSelect = vi.fn();
    const { rerender } = renderWithProviders(
      <BriefingHistoryList selectedId={null} onSelect={onSelect} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /view briefing from 2026-09-05/i }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 7, synthesis_text: "s7" }));

    rerender(<BriefingHistoryList selectedId={7} onSelect={onSelect} />);
    const viewing = await screen.findByRole("button", { name: /viewing briefing from 2026-09-05/i });
    expect(viewing).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(viewing);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("pages forward when the server reports a next page", async () => {
    api = mockApi({
      "GET /api/briefings/": (_body: unknown, url: string) =>
        url.includes("page=2")
          ? { count: 21, next: null, previous: "p1", results: [run(1, "2026-08-01")] }
          : { count: 21, next: "p2", previous: null, results: [run(21, "2026-09-21")] },
    });
    renderWithProviders(<BriefingHistoryList selectedId={null} onSelect={vi.fn()} />);
    const next = await screen.findByRole("button", { name: /next page/i });
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
    fireEvent.click(next);
    await waitFor(() => expect(screen.getByText("2026-08-01")).toBeInTheDocument());
    expect(screen.getByText("21–21 of 21")).toBeInTheDocument();
  });
});
