/**
 * Page-level testid smoke tests.
 *
 * Each test mocks fetch to return a minimal list, renders the page, and
 * asserts that the expected data-testid attribute is present.
 *
 * Strategy: mock fetch globally (the pattern existing tests already use),
 * then render the page through the shared renderWithProviders helper.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/hooks/useToast";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// Stub WebSocket so components that open sockets don't throw.
// Must include addEventListener since WebSocketProvider uses it.
beforeEach(() => {
  (globalThis as { WebSocket?: unknown }).WebSocket = vi.fn(() => ({
    onmessage: null,
    onerror: null,
    onopen: null,
    onclose: null,
    close: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    send: vi.fn(),
  }));
});

// ---------------------------------------------------------------------------
// SchedulesPage — schedule-row-<id>
// ---------------------------------------------------------------------------

describe("SchedulesPage", () => {
  it("renders schedule-row-<id>", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("/api/observer/schedules/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: 42, name: "Hourly", profile: 1, enabled: true,
                market_hours_only: true, objective_template: "",
                cron_display: "0 * * * *", last_fired_at: null,
                created_at: "2026-04-17T00:00:00Z",
                updated_at: "2026-04-17T00:00:00Z",
              },
            ]),
        });
      }
      if (url.includes("/api/profiles/")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "P", default_includes: [] }]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    }) as never;

    const { default: SchedulesPage } = await import("../../pages/SchedulesPage");
    wrap(<SchedulesPage />);
    expect(await screen.findByTestId("schedule-row-42")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// TriggersListPage — trigger-row-<id>
// ---------------------------------------------------------------------------

describe("TriggersListPage", () => {
  it("renders trigger-row-<id>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 7, name: "RSI cross", enabled: true,
              condition: { all: [] }, last_fired_at: null,
              firings_count: 3,
            },
          ]),
      }),
    ) as never;

    const { default: TriggersListPage } = await import("../../pages/TriggersListPage");
    wrap(<TriggersListPage />);
    expect(await screen.findByTestId("trigger-row-7")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ThreadsPage — thread-row-<id>
// ---------------------------------------------------------------------------

describe("ThreadsPage", () => {
  it("renders thread-row-<id>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 55, title: "Morning consult", kind: "consult",
              profile: { name: "Day trader" },
              created_at: "2026-04-17T09:00:00Z",
            },
          ]),
      }),
    ) as never;

    const { default: ThreadsPage } = await import("../../pages/ThreadsPage");
    wrap(<ThreadsPage />);
    expect(await screen.findByTestId("thread-row-55")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WatchlistsList — watchlist-row-<name>
// ---------------------------------------------------------------------------

describe("WatchlistsList", () => {
  it("renders watchlist-row-<name>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            { id: 1, name: "Tech", symbols: [{ ticker: "AAPL" }] },
          ]),
      }),
    ) as never;

    const { default: WatchlistsList } = await import("../../pages/WatchlistsList");
    wrap(<WatchlistsList />);
    expect(await screen.findByTestId("watchlist-row-Tech")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ProfilesPage — profile-row-<name>
// ---------------------------------------------------------------------------

describe("ProfilesPage", () => {
  it("renders profile-row-<name>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 2, name: "Swing", style: "swing trading",
              default_includes: ["quotes"], default_provider: "claude",
              default_model: "claude-sonnet-4-6",
            },
          ]),
      }),
    ) as never;

    const { default: ProfilesPage } = await import("../../pages/ProfilesPage");
    wrap(<ProfilesPage />);
    expect(await screen.findByTestId("profile-row-Swing")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BackupsPage — backup-row-<id>
// ---------------------------------------------------------------------------

describe("BackupsPage", () => {
  it("renders backup-row-<id>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 11, status: "ok", kind: "scheduled",
              filename: "backup_11.dump",
              size_bytes: 1024 * 500,
              created_at: "2026-04-17T02:30:00Z",
              error: null,
            },
          ]),
      }),
    ) as never;

    const { default: BackupsPage } = await import("../../pages/BackupsPage");
    wrap(<BackupsPage />);
    expect(await screen.findByTestId("backup-row-11")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ExportPage — export-row-<id>
// ---------------------------------------------------------------------------

describe("ExportPage", () => {
  it("renders export-row-<id>", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 3, status: "done", size_bytes: 2048,
              filename: "export_3.zip",
              created_at: "2026-04-17T10:00:00Z",
              scope: {},
              error: null,
            },
          ]),
      }),
    ) as never;

    const { default: ExportPage } = await import("../../pages/ExportPage");
    wrap(<ExportPage />);
    expect(await screen.findByTestId("export-row-3")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// AnalyticsPage — analytics-card-<kind>
// ---------------------------------------------------------------------------

describe("AnalyticsPage", () => {
  it("renders analytics-card-leaderboard", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    ) as never;

    const { default: AnalyticsPage } = await import("../../pages/AnalyticsPage");
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-leaderboard")).toBeInTheDocument();
  });

  it("renders analytics-card-cpi", async () => {
    const { default: AnalyticsPage } = await import("../../pages/AnalyticsPage");
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-cpi")).toBeInTheDocument();
  });

  it("renders analytics-card-heatmap", async () => {
    const { default: AnalyticsPage } = await import("../../pages/AnalyticsPage");
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-heatmap")).toBeInTheDocument();
  });

  it("renders analytics-card-timeline", async () => {
    const { default: AnalyticsPage } = await import("../../pages/AnalyticsPage");
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-timeline")).toBeInTheDocument();
  });

  it("renders analytics-card-unusual-options", async () => {
    const { default: AnalyticsPage } = await import("../../pages/AnalyticsPage");
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-unusual-options")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// SnapshotComposerPage — capture-btn, send-ai-btn
// ---------------------------------------------------------------------------

describe("SnapshotComposerPage", () => {
  it("renders capture-btn", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("/api/profiles/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              { id: 1, name: "P", default_includes: ["quotes"], default_provider: "claude", default_model: "claude-sonnet-4-6" },
            ]),
        });
      }
      if (url.includes("/api/watchlists/")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: 1, name: "Tech", symbols: [] }]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    }) as never;

    const { default: SnapshotComposerPage } = await import("../../pages/SnapshotComposerPage");
    wrap(<SnapshotComposerPage />);
    expect(await screen.findByTestId("capture-btn")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ThreadDetailPage — compose-input, message-<id>
// ---------------------------------------------------------------------------

describe("ThreadDetailPage", () => {
  it("renders compose-input", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("/api/threads/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: 1, title: "Test thread", kind: "consult",
              profile: { id: 1, name: "P" },
              messages: [
                {
                  id: 100, role: "user", status: "done",
                  content: { text: "Hello" }, ai_run: null, error: null,
                },
              ],
              created_at: "2026-04-17T09:00:00Z",
            }),
        });
      }
      if (url.includes("/api/files/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }) as never;

    const { default: ThreadDetailPage } = await import("../../pages/ThreadDetailPage");
    // ThreadDetailPage uses useParams + useChannel (WebSocket) — needs full providers
    render(
      <QueryClientProvider client={makeQc()}>
        <ToastProvider>
          <WebSocketProvider>
            <MemoryRouter initialEntries={["/threads/1"]}>
              <Routes>
                <Route path="/threads/:id" element={<ThreadDetailPage />} />
              </Routes>
            </MemoryRouter>
          </WebSocketProvider>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("compose-input")).toBeInTheDocument();
  });

  it("renders message-<id> for each message", async () => {
    globalThis.fetch = vi.fn((url: string) => {
      if (url.includes("/api/threads/")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: 1, title: "Test thread", kind: "consult",
              profile: { id: 1, name: "P" },
              messages: [
                {
                  id: 100, role: "user", status: "done",
                  content: { text: "Hello" }, ai_run: null, error: null,
                },
                {
                  id: 101, role: "assistant", status: "done",
                  content: { text: "Reply" },
                  ai_run: { cost_usd: "0.001", model: "claude-sonnet-4-6", provider: "claude" },
                  error: null,
                },
              ],
              created_at: "2026-04-17T09:00:00Z",
            }),
        });
      }
      if (url.includes("/api/files/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }) as never;

    const { default: ThreadDetailPage } = await import("../../pages/ThreadDetailPage");
    render(
      <QueryClientProvider client={makeQc()}>
        <ToastProvider>
          <WebSocketProvider>
            <MemoryRouter initialEntries={["/threads/1"]}>
              <Routes>
                <Route path="/threads/:id" element={<ThreadDetailPage />} />
              </Routes>
            </MemoryRouter>
          </WebSocketProvider>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("message-100")).toBeInTheDocument();
    expect(screen.getByTestId("message-101")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BranchTabs — branch-cost-<n>  (already present per spec; just confirm)
// ---------------------------------------------------------------------------

describe("BranchTabs", () => {
  it("renders branch-cost-<id> when cost is set", async () => {
    const { default: BranchTabs } = await import("../../components/BranchTabs");
    render(
      <MemoryRouter>
        <BranchTabs
          branches={[{ id: 9, label: "claude/sonnet", status: "done", cost: 0.0012 }]}
          activeId={9}
          onSelect={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("branch-cost-9")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Citation — citation-<index>
// ---------------------------------------------------------------------------

describe("Citation", () => {
  it("renders citation-<index>", async () => {
    const { Citation } = await import("../../components/Citation");
    render(
      <MemoryRouter>
        <Citation index={3} source="https://example.com" title="Example" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("citation-3")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// FileAttachPanel — file-row-<id>
// ---------------------------------------------------------------------------

describe("FileAttachPanel", () => {
  it("renders file-row-<id>", async () => {
    const { FileAttachPanel } = await import("../../components/FileAttachPanel");
    render(
      <MemoryRouter>
        <FileAttachPanel
          threadId={1}
          files={[
            { id: 22, filename: "report.pdf", kind: "document", ticker: "", mime: "application/pdf", size: 1024 },
          ]}
          onAttach={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("file-row-22")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// DailyCostChart — cost-tile-today
// ---------------------------------------------------------------------------

describe("DailyCostChart", () => {
  it("renders cost-tile-today wrapper", async () => {
    const { default: DailyCostChart } = await import("../../components/costs/DailyCostChart");
    render(
      <DailyCostChart
        data={[{ date: "2026-04-17", cost_usd: "1.23", runs: 5 }]}
      />,
    );
    expect(screen.getByTestId("cost-tile-today")).toBeInTheDocument();
  });
});
