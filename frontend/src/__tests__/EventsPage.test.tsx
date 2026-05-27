import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import EventsPage from "@/pages/EventsPage";
import { useWatchlists } from "@/hooks/useWatchlists";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";

vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: vi.fn(),
}));

vi.mock("@/hooks/useUpcomingEvents", () => ({
  useUpcomingEvents: vi.fn(),
}));

const mockUseWatchlists = vi.mocked(useWatchlists);
const mockUseUpcomingEvents = vi.mocked(useUpcomingEvents);

const emptyEvents = {
  data: { earnings: [], macro: [] },
  isLoading: false,
  isSuccess: true,
  isError: false,
} as unknown as ReturnType<typeof useUpcomingEvents>;

describe("EventsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseWatchlists.mockReturnValue({
      data: [],
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useWatchlists>);
    mockUseUpcomingEvents.mockReturnValue(emptyEvents);
  });

  it("shows the skeleton while loading", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    const { container } = renderWithProviders(<EventsPage />);
    // SkeletonRows renders animated placeholder divs; the main page content should not appear
    expect(screen.queryByText("Upcoming earnings")).not.toBeInTheDocument();
    expect(screen.queryByText("Macro calendar")).not.toBeInTheDocument();
    // There should be some skeleton content in the container
    expect(container.firstChild).not.toBeNull();
  });

  it("shows EmptyState for both sections when there are no events", () => {
    renderWithProviders(<EventsPage />);

    expect(screen.getByText("No upcoming earnings")).toBeInTheDocument();
    expect(screen.getByText("No macro events")).toBeInTheDocument();
    expect(screen.getByText(/across your watchlists in the next 30 days/i)).toBeInTheDocument();
    expect(screen.getByText(/no high-impact US events/i)).toBeInTheDocument();
  });

  it("shows section headings in the populated layout", () => {
    renderWithProviders(<EventsPage />);

    expect(screen.getByText("Upcoming earnings")).toBeInTheDocument();
    expect(screen.getByText("Macro calendar")).toBeInTheDocument();
    expect(screen.getByText("Market Calendar")).toBeInTheDocument();
  });

  it("lists earnings rows when earnings are present", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: {
        earnings: [
          {
            kind: "earnings",
            ticker: "AAPL",
            title: "AAPL earnings",
            event_time: "2026-06-01T20:00:00Z",
            days_until: 5,
            when_hint: "amc",
            impact: "high",
            detail: { eps_est: 1.55 },
          },
          {
            kind: "earnings",
            ticker: "MSFT",
            title: "MSFT earnings",
            event_time: "2026-06-05T20:00:00Z",
            days_until: 9,
            when_hint: "bmo",
            impact: "high",
            detail: {},
          },
        ],
        macro: [],
      },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    renderWithProviders(<EventsPage />);

    expect(screen.getByText(/AAPL earnings \(AMC\)/)).toBeInTheDocument();
    expect(screen.getByText(/MSFT earnings \(BMO\)/)).toBeInTheDocument();
    // EPS estimate appears for AAPL
    expect(screen.getByText(/est EPS 1.55/)).toBeInTheDocument();
    // No-macro empty state still shows
    expect(screen.getByText("No macro events")).toBeInTheDocument();
  });

  it("lists macro rows when macro events are present", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: {
        earnings: [],
        macro: [
          {
            kind: "macro",
            ticker: "",
            title: "CPI Report",
            event_time: "2026-06-03T12:30:00Z",
            days_until: 7,
            when_hint: "",
            impact: "high",
            detail: {},
          },
        ],
      },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    renderWithProviders(<EventsPage />);

    expect(screen.getByText("CPI Report")).toBeInTheDocument();
    expect(screen.getByText(/in 7d/)).toBeInTheDocument();
    // No-earnings empty state still shows
    expect(screen.getByText("No upcoming earnings")).toBeInTheDocument();
  });

  it("passes tickers from watchlists to useUpcomingEvents", () => {
    mockUseWatchlists.mockReturnValue({
      data: [
        {
          id: 1,
          name: "Tech",
          created_at: "2026-01-01T00:00:00Z",
          symbols: [
            { id: 1, ticker: "AAPL", sort_order: 0 },
            { id: 2, ticker: "GOOG", sort_order: 1 },
          ],
        },
      ],
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useWatchlists>);

    renderWithProviders(<EventsPage />);

    expect(mockUseUpcomingEvents).toHaveBeenCalledWith(["AAPL", "GOOG"], 30);
  });
});
