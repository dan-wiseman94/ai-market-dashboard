import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import type { Briefing } from "@/api/briefing";
import BriefingPage from "@/pages/BriefingPage";
import * as briefingHooks from "@/hooks/useBriefing";
import * as profileHooks from "@/hooks/useProfiles";
import { renderWithProviders } from "./testUtils";

const CONFIG = {
  enabled: true, synthesis_enabled: true, send_at_local: "08:30:00", profile: null,
  news_lookback_hours: 14, events_within_days: 7, updated_at: "2026-09-01T00:00:00Z",
};
const EMPTY_DATA = {
  theses: [], events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x",
};

function mockPage(latest: unknown, history: Briefing[] = [], isLoading = false) {
  vi.spyOn(briefingHooks, "useLatestBriefing").mockReturnValue({ data: latest, isLoading } as never);
  vi.spyOn(briefingHooks, "useRunBriefing").mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  vi.spyOn(briefingHooks, "useBriefings").mockReturnValue({
    data: { count: history.length, next: null, previous: null, results: history },
    isLoading: false, isError: false,
  } as never);
  vi.spyOn(briefingHooks, "useBriefingConfig").mockReturnValue({
    data: CONFIG, isLoading: false, isError: false,
    update: { mutate: vi.fn(), isPending: false },
  } as never);
  vi.spyOn(profileHooks, "useProfiles").mockReturnValue({ data: [] } as never);
}

describe("BriefingPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state with no briefing — and still exposes settings + history", () => {
    mockPage(null);
    renderWithProviders(<BriefingPage />);
    expect(screen.getByText(/No briefing yet/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Run the morning briefing automatically/i)).toBeInTheDocument();
    expect(screen.getByText(/No past briefings/i)).toBeInTheDocument();
  });

  it("does not crash on a failed run with empty data", () => {
    mockPage({
      id: 2, status: "failed", created_at: "x", scheduled_date: null, snapshot: null,
      synthesis_text: "", synthesis_status: "", data: {},
    });
    renderWithProviders(<BriefingPage />);
    expect(screen.getByText(/failed to assemble/i)).toBeInTheDocument();
  });

  it("renders synthesis + theses when populated", () => {
    mockPage({
      id: 1, status: "ready", created_at: "x", scheduled_date: null, snapshot: null,
      synthesis_text: "Lead with NVDA.", synthesis_status: "done",
      data: {
        theses: [{ id: 1, ticker: "NVDA", direction: "bullish", conviction: 4,
          entry: null, target: 110, invalidation: 90, current: 100, pct_to_target: 10,
          pct_to_invalidation: -10 }],
        events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x",
      },
    });
    renderWithProviders(<BriefingPage />);
    expect(screen.getByText("Lead with NVDA.")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("drills into a past briefing and back to latest", async () => {
    const past: Briefing = {
      id: 5, created_at: "2026-09-01T12:00:00Z", status: "ready", scheduled_date: "2026-09-01",
      snapshot: null, data: EMPTY_DATA, synthesis_text: "Older read.", synthesis_status: "done",
    };
    mockPage(
      { id: 9, created_at: "2026-09-10T12:00:00Z", status: "ready", scheduled_date: "2026-09-10",
        snapshot: null, data: EMPTY_DATA, synthesis_text: "Latest read.", synthesis_status: "done" },
      [past],
    );
    renderWithProviders(<BriefingPage />);
    expect(screen.getByText("Latest read.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /view briefing from 2026-09-01/i }));
    await waitFor(() => expect(screen.getByText("Older read.")).toBeInTheDocument());
    expect(screen.getByText(/Viewing the briefing from 2026-09-01/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /back to latest/i }));
    await waitFor(() => expect(screen.getByText("Latest read.")).toBeInTheDocument());
  });
});
