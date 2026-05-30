import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import Dashboard from "@/pages/Dashboard";

// ---------------------------------------------------------------------------
// Child component mocks — keep test surface flat
// ---------------------------------------------------------------------------

vi.mock("@/hooks/useMarketContext", () => ({
  useMarketContext: vi.fn(() => ({ data: null, isLoading: false })),
}));

vi.mock("@/hooks/usePositions", () => ({
  usePositions: vi.fn(() => ({ data: [], isLoading: false, error: null })),
}));

vi.mock("@/hooks/useCosts", () => ({
  useCostsToday: vi.fn(() => ({ data: null })),
}));

const mockMarketStatus = vi.fn();
vi.mock("@/hooks/useMarketStatus", () => ({
  useMarketStatus: () => mockMarketStatus(),
}));

// useDashboard is the new boundary — mock it at the hook level
const mockUseDashboard = vi.fn();
vi.mock("@/hooks/useDashboard", () => ({
  useDashboard: () => mockUseDashboard(),
}));

const DASHBOARD_PAYLOAD = {
  theses: [
    {
      id: 1,
      ticker: "AAPL",
      direction: "bullish",
      conviction: 4,
      entry: 170.0,
      target: 200.0,
      invalidation: 155.0,
      current: 185.0,
      pct_to_target: 8.11,
      pct_to_invalidation: -16.22,
    },
  ],
  events: {
    earnings: [
      {
        kind: "earnings",
        ticker: "NVDA",
        title: "NVDA earnings (BMO)",
        event_time: "2026-06-01T13:00:00+00:00",
        days_until: 2,
        when_hint: "bmo",
        impact: "high",
        detail: {},
      },
    ],
    macro: [],
  },
  observer: { enabled_schedules: 3, runs_today: 5 },
  triggers: {
    armed_count: 7,
    latest_firings: [
      {
        id: 42,
        trigger_id: 10,
        trigger_name: "SPY drop",
        fired_at: "2026-05-30T09:45:00Z",
        cost_capped: false,
      },
    ],
  },
  briefing: {
    id: 99,
    status: "ready",
    created_at: "2026-05-30T08:00:00Z",
    scheduled_date: "2026-05-30",
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockMarketStatus.mockReturnValue({
    data: { markets: { us_equity: { is_open: true, phase: "open" } } },
  });
  mockUseDashboard.mockReturnValue({
    data: DASHBOARD_PAYLOAD,
    isLoading: false,
  });
});

describe("Dashboard", () => {
  it("renders without crashing", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("includes a time-based greeting in the hero heading", () => {
    renderWithProviders(<Dashboard />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/good morning|good afternoon|good evening|late watch/i);
  });

  it("hero headline says the tape is open during the regular session", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: true, phase: "open" } } },
    });
    renderWithProviders(<Dashboard />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/the tape is open/i);
  });

  it("hero reflects extended hours (headline + status) instead of 'open'", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: false, phase: "postmarket" } } },
    });
    renderWithProviders(<Dashboard />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/the tape is in extended hours/i);
    expect(heading.textContent).not.toMatch(/the tape is open/i);
    expect(screen.getByText("Extended Hours")).toBeInTheDocument();
  });

  it("hero says the tape is closed when the market is closed", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: false, phase: "weekend" } } },
    });
    renderWithProviders(<Dashboard />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/the tape is closed/i);
  });

  it("includes the 'Market context' section label", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/market context/i)).toBeInTheDocument();
  });

  it("includes the 'The book' section label (positions area)", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/the book/i)).toBeInTheDocument();
  });

  it("includes a 'Capture snapshot' call-to-action link", () => {
    renderWithProviders(<Dashboard />);
    const ctaLink = screen.getByRole("link", { name: /capture snapshot/i });
    expect(ctaLink).toBeInTheDocument();
    expect(ctaLink).toHaveAttribute("href", "/snapshot");
  });

  it("includes a 'Watchlists' navigation link in the book section", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByRole("link", { name: /watchlists/i })).toBeInTheDocument();
  });

  // ------------------------------------------------------------------
  // Command-centre tiles — real content assertions (W4b)
  // ------------------------------------------------------------------

  it("shows the AAPL thesis from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("shows armed triggers count from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByTestId("triggers-armed-count").textContent).toBe("7");
  });

  it("shows latest firing name from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText("SPY drop")).toBeInTheDocument();
  });

  it("shows observer runs_today from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("5");
  });

  it("shows briefing status badge from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    // The BriefingSummaryTile shows a 'ready' badge
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("shows upcoming NVDA earnings event from useDashboard", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/NVDA earnings/i)).toBeInTheDocument();
  });

  it("shows Skeleton rows while useDashboard is loading", () => {
    mockUseDashboard.mockReturnValue({ data: undefined, isLoading: true });
    renderWithProviders(<Dashboard />);
    // SkeletonRows renders data-testid="skeleton-row"
    const rows = screen.getAllByTestId("skeleton-row");
    expect(rows.length).toBeGreaterThan(0);
  });

  it("shows 'Command centre' section heading", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/command centre/i)).toBeInTheDocument();
  });
});
