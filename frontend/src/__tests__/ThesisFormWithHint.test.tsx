import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import ThesisForm from "@/pages/thread-detail/ThesisForm";
import * as analytics from "@/hooks/useAnalytics";
import type { TrackRecord } from "@/hooks/useAnalytics";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const FULL_RECORD: TrackRecord = {
  ticker: "NVDA",
  closed_n: 5,
  counts: { win: 3, loss: 2, scratch: 0, invalidated: 0 },
  hit_rate: 0.6,
  last: { direction: "bullish", conviction: 3, status: "closed_win" },
  slice: null,
};

const BASE_PROPS = {
  promoteMode: false,
  title: "Test thesis",
  onTitleChange: vi.fn(),
  ticker: "NVDA",
  onTickerChange: vi.fn(),
  direction: "bullish" as const,
  onDirectionChange: vi.fn(),
  conviction: 3,
  onConvictionChange: vi.fn(),
  target: "",
  onTargetChange: vi.fn(),
  invalidation: "",
  onInvalidationChange: vi.fn(),
  pending: false,
  onSubmit: vi.fn(),
  onCancel: vi.fn(),
};

describe("ThesisForm with TrackRecordHint", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the track-record hint when useTrackRecord returns available=true", () => {
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: true, record: FULL_RECORD },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    render(<ThesisForm {...BASE_PROPS} />, { wrapper });

    expect(screen.getByTestId("track-record-hint")).toBeInTheDocument();
    expect(screen.getByText(/Your NVDA track record:/)).toBeInTheDocument();
    expect(screen.getByText(/5 closed/)).toBeInTheDocument();
    expect(screen.getByText(/3W \/ 2L/)).toBeInTheDocument();
  });

  it("does NOT show the hint when useTrackRecord returns available=false", () => {
    vi.spyOn(analytics, "useTrackRecord").mockReturnValue({
      data: { ticker: "NVDA", available: false, record: null },
      isLoading: false,
      isSuccess: true,
    } as ReturnType<typeof analytics.useTrackRecord>);

    render(<ThesisForm {...BASE_PROPS} />, { wrapper });

    expect(screen.queryByTestId("track-record-hint")).toBeNull();
  });
});
