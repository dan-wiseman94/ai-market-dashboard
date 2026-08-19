import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import { ToastProvider } from "@/hooks/useToast";
import { Toasts } from "@/components/Toasts";
import Dashboard from "@/pages/Dashboard";
import { installFakeWebSocket, type FakeWebSocketController } from "./testUtils";

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
  regime: {
    composite: "Neutral-Transitional",
    drivers: ["VIX 18 — Normal"],
    as_of: "2026-05-30T12:00:00Z",
  },
  book: { hhi: 0.4, alignment: "aligned", as_of: "2026-06-01" },
  desk: { unread: 0, latest: null },
};

let fake: FakeWebSocketController;

beforeEach(() => {
  fake = installFakeWebSocket();
  vi.clearAllMocks();
  mockMarketStatus.mockReturnValue({
    data: { markets: { us_equity: { is_open: true, phase: "open" } } },
  });
  mockUseDashboard.mockReturnValue({
    data: DASHBOARD_PAYLOAD,
    isLoading: false,
  });
});

afterEach(() => {
  fake.restore();
});

/**
 * Dashboard uses useChannel → useWebSocket → requires WebSocketProvider.
 * Wrap with the full provider tree including the shared WS broker.
 */
function renderDashboard(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <WebSocketProvider>
        <ToastProvider>
          <Toasts />
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </WebSocketProvider>
    </QueryClientProvider>,
  );
  return client;
}

describe("Dashboard", () => {
  it("renders without crashing", () => {
    renderDashboard();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("includes a time-based greeting in the hero heading", () => {
    renderDashboard();
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/good morning|good afternoon|good evening|late watch/i);
  });

  it("hero headline says the tape is open during the regular session", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: true, phase: "open" } } },
    });
    renderDashboard();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/the tape is open/i);
  });

  it("hero reflects extended hours (headline + status) instead of 'open'", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: false, phase: "postmarket" } } },
    });
    renderDashboard();
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/the tape is in extended hours/i);
    expect(heading.textContent).not.toMatch(/the tape is open/i);
    expect(screen.getByText("Extended Hours")).toBeInTheDocument();
  });

  it("hero says the tape is closed when the market is closed", () => {
    mockMarketStatus.mockReturnValue({
      data: { markets: { us_equity: { is_open: false, phase: "weekend" } } },
    });
    renderDashboard();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/the tape is closed/i);
  });

  it("includes the 'Market context' section label", () => {
    renderDashboard();
    expect(screen.getByText(/market context/i)).toBeInTheDocument();
  });

  it("includes the 'The book' section label (positions area)", () => {
    renderDashboard();
    // "The book" appears in both the h2 section heading and the PositionsBookTile eyebrow
    expect(screen.getAllByText(/the book/i).length).toBeGreaterThanOrEqual(1);
  });

  it("includes a 'Capture snapshot' call-to-action link", () => {
    renderDashboard();
    const ctaLink = screen.getByRole("link", { name: /capture snapshot/i });
    expect(ctaLink).toBeInTheDocument();
    expect(ctaLink).toHaveAttribute("href", "/snapshot");
  });

  it("includes a 'Watchlists' navigation link in the book section", () => {
    renderDashboard();
    expect(screen.getByRole("link", { name: /watchlists/i })).toBeInTheDocument();
  });

  it("shows the AAPL thesis from useDashboard", () => {
    renderDashboard();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("shows armed triggers count from useDashboard", () => {
    renderDashboard();
    expect(screen.getByTestId("triggers-armed-count").textContent).toBe("7");
  });

  it("shows latest firing name from useDashboard", () => {
    renderDashboard();
    expect(screen.getByText("SPY drop")).toBeInTheDocument();
  });

  it("shows observer runs_today from useDashboard", () => {
    renderDashboard();
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("5");
  });

  it("shows briefing status badge from useDashboard", () => {
    renderDashboard();
    // The BriefingSummaryTile shows a 'ready' badge
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("shows upcoming NVDA earnings event from useDashboard", () => {
    renderDashboard();
    expect(screen.getByText(/NVDA earnings/i)).toBeInTheDocument();
  });

  it("shows Skeleton rows while useDashboard is loading", () => {
    mockUseDashboard.mockReturnValue({ data: undefined, isLoading: true });
    renderDashboard();
    // SkeletonRows renders data-testid="skeleton-row"
    const rows = screen.getAllByTestId("skeleton-row");
    expect(rows.length).toBeGreaterThan(0);
  });

  it("shows 'Command centre' section heading", () => {
    renderDashboard();
    expect(screen.getByText(/command centre/i)).toBeInTheDocument();
  });

  it("invalidates the dashboard query when a notification.event arrives over /ws/notifications/", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    renderDashboard(client);

    // The shared WebSocketProvider opens /ws/notifications/ because Dashboard
    // subscribes to the "notifications" channel via useChannel.
    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();

    act(() => {
      sock!.emitMessage({
        type: "notification.event",
        payload: { kind: "observer_done", title: "Observer ran" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["dashboard"] }),
    );
  });

  it("does not invalidate dashboard query on non-notification messages", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    renderDashboard(client);

    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();

    act(() => {
      sock!.emitMessage({ type: "text_delta", text: "x" });
    });

    expect(invalidateSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["dashboard"] }),
    );
  });
});
