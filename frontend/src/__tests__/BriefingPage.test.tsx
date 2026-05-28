import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BriefingPage from "@/pages/BriefingPage";
import * as hooks from "@/hooks/useBriefing";

function mockLatest(value: unknown, isLoading = false) {
  vi.spyOn(hooks, "useLatestBriefing").mockReturnValue({ data: value, isLoading } as never);
  vi.spyOn(hooks, "useRunBriefing").mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
}

describe("BriefingPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state with no briefing", () => {
    mockLatest(null);
    render(<MemoryRouter><BriefingPage /></MemoryRouter>);
    expect(screen.getByText(/No briefing yet/i)).toBeInTheDocument();
  });

  it("does not crash on a failed run with empty data", () => {
    mockLatest({
      id: 2, status: "failed", created_at: "x", scheduled_date: null, snapshot: null,
      synthesis_text: "", synthesis_status: "", data: {},
    });
    render(<MemoryRouter><BriefingPage /></MemoryRouter>);
    expect(screen.getByText(/failed to assemble/i)).toBeInTheDocument();
  });

  it("renders synthesis + theses when populated", () => {
    mockLatest({
      id: 1, status: "ready", created_at: "x", scheduled_date: null, snapshot: null,
      synthesis_text: "Lead with NVDA.", synthesis_status: "done",
      data: {
        theses: [{ id: 1, ticker: "NVDA", direction: "bullish", conviction: 4,
          entry: null, target: 110, invalidation: 90, current: 100, pct_to_target: 10,
          pct_to_invalidation: -10 }],
        events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x",
      },
    });
    render(<MemoryRouter><BriefingPage /></MemoryRouter>);
    expect(screen.getByText("Lead with NVDA.")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });
});
