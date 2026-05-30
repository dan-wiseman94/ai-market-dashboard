import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { TrackRecordHint } from "@/components/TrackRecordHint";
import * as analytics from "@/hooks/useAnalytics";
import type { TrackRecord } from "@/hooks/useAnalytics";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const FULL_RECORD: TrackRecord = {
  ticker: "NVDA",
  closed_n: 3,
  counts: { win: 2, loss: 1, scratch: 0, invalidated: 0 },
  hit_rate: 0.6667,
  last: { direction: "bullish", conviction: 4, status: "closed_win" },
  slice: { direction: "bullish", conviction: 4, correct: 2, n: 2, hit_rate: 1.0 },
};

describe("TrackRecordHint", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the summary text when available=true", () => {
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: true, record: FULL_RECORD },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    render(<TrackRecordHint ticker="NVDA" />, { wrapper });

    // testid present
    expect(screen.getByTestId("track-record-hint")).toBeInTheDocument();
    // ticker label
    expect(screen.getByText(/Your NVDA track record:/)).toBeInTheDocument();
    // closed count
    expect(screen.getByText(/3 closed/)).toBeInTheDocument();
    // win/loss counts
    expect(screen.getByText(/2W \/ 1L/)).toBeInTheDocument();
    // hit rate percentage
    expect(screen.getByText(/67%/)).toBeInTheDocument();
    // slice conviction text
    expect(screen.getByText(/Conviction-4 bullish: 2\/2 correct/)).toBeInTheDocument();
  });

  it("renders nothing when available=false", () => {
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "XYZ", available: false, record: null },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    const { container } = render(<TrackRecordHint ticker="XYZ" />, { wrapper });

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId("track-record-hint")).toBeNull();
  });

  it("renders nothing when data is undefined (loading)", () => {
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
    } as ReturnType<typeof analytics.useTrackRecord>);

    const { container } = render(<TrackRecordHint ticker="NVDA" />, { wrapper });

    expect(container.firstChild).toBeNull();
  });

  it("renders without slice line when slice is null", () => {
    const noSliceRecord: TrackRecord = { ...FULL_RECORD, slice: null };
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: true, record: noSliceRecord },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    render(<TrackRecordHint ticker="NVDA" />, { wrapper });

    expect(screen.getByTestId("track-record-hint")).toBeInTheDocument();
    expect(screen.getByText(/2W \/ 1L/)).toBeInTheDocument();
    // No slice text
    expect(screen.queryByText(/Conviction-4/)).toBeNull();
  });
});
