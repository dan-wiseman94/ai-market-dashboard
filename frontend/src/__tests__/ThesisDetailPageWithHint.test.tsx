import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ThesisDetailPage from "@/pages/ThesisDetailPage";
import * as analytics from "@/hooks/useAnalytics";
import { mockApi, renderWithProviders } from "./testUtils";
import type { TrackRecord } from "@/hooks/useAnalytics";
import type { PostMortem } from "@/api/thesis";

// Stub ThesisChart so these page-level tests don't need to mock the OHLC endpoint.
vi.mock("@/components/ThesisChart", () => ({
  default: ({ ticker }: { ticker: string }) => (
    <div data-testid="thesis-chart-stub" data-ticker={ticker} />
  ),
}));

const THESIS = {
  id: 5,
  title: "NVDA breakout",
  ticker: "NVDA",
  direction: "bullish" as const,
  rationale: "AI demand drives upside",
  conviction: 4,
  entry_price: "900.00",
  target_price: "1100.00",
  invalidation_price: "820.00",
  horizon_days: 60,
  status: "open" as const,
  profile_id: null,
  thread_id: null,
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

const TRACK_RECORD: TrackRecord = {
  ticker: "NVDA",
  closed_n: 4,
  counts: { win: 3, loss: 1, scratch: 0, invalidated: 0 },
  hit_rate: 0.75,
  last: { direction: "bullish", conviction: 4, status: "closed_win" },
  slice: null,
};

describe("ThesisDetailPage with TrackRecordHint", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the track-record hint when useTrackRecord returns available=true", async () => {
    mockApi({ "GET /api/theses/5/": THESIS });
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: true, record: TRACK_RECORD },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/5"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByText("NVDA breakout")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("track-record-hint")).toBeInTheDocument();
    expect(screen.getByText(/Your NVDA track record:/)).toBeInTheDocument();
    expect(screen.getByText(/4 closed/)).toBeInTheDocument();
    expect(screen.getByText(/3W \/ 1L/)).toBeInTheDocument();
    expect(screen.getByText(/75%/)).toBeInTheDocument();
  });

  it("does NOT show hint when useTrackRecord returns available=false", async () => {
    mockApi({ "GET /api/theses/5/": THESIS });
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: false, record: null },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/5"],
      routePath: "/theses/:id",
    });

    await waitFor(() =>
      expect(screen.getByText("NVDA breakout")).toBeInTheDocument(),
    );

    expect(screen.queryByTestId("track-record-hint")).toBeNull();
  });
});
