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
import { describe, it, expect, beforeEach } from "vitest";
import { installFakeWebSocket, mockFetch, renderWithProviders } from "../testUtils";

// Pages and components are imported statically (not via `await import()` inside
// each test). A dynamic import in the test body runs while the per-test
// `testTimeout` clock is ticking, so the first-time load of a heavy dependency
// graph (e.g. ThreadsPage → date-fns) gets charged against the test's deadline.
// Under the parallel CPU load of a full `pnpm test --run`, that load cost can
// exceed the timeout and fail an otherwise-correct test (see ThreadsPage flake).
// Static imports are resolved during file collection, before any test timer
// starts, so module-load cost never counts toward a test's budget.
import SchedulesPage from "../../pages/SchedulesPage";
import TriggersListPage from "../../pages/TriggersListPage";
import ThreadsPage from "../../pages/ThreadsPage";
import WatchlistsList from "../../pages/WatchlistsList";
import ProfilesPage from "../../pages/ProfilesPage";
import BackupsPage from "../../pages/BackupsPage";
import ExportPage from "../../pages/ExportPage";
import AnalyticsPage from "../../pages/AnalyticsPage";
import SnapshotComposerPage from "../../pages/SnapshotComposerPage";
import ThreadDetailPage from "../../pages/ThreadDetailPage";
import BranchTabs from "../../components/BranchTabs";
import { Citation } from "../../components/Citation";
import { FileAttachPanel } from "../../components/FileAttachPanel";
import DailyCostChart from "../../components/costs/DailyCostChart";

// Stub WebSocket so components that open sockets don't throw.
beforeEach(() => {
  installFakeWebSocket();
});

describe("SchedulesPage", () => {
  it("renders schedule-row-<id>", async () => {
    mockFetch((url) => ({
      ok: true,
      json: async () => {
        if (url.includes("/api/observer/schedules/")) {
          return [
            {
              id: 42, name: "Hourly", profile: 1, enabled: true,
              market_hours_only: true, objective_template: "",
              cron_display: "0 * * * *", last_fired_at: null,
              created_at: "2026-04-17T00:00:00Z",
              updated_at: "2026-04-17T00:00:00Z",
            },
          ];
        }
        if (url.includes("/api/profiles/")) {
          return [{ id: 1, name: "P", default_includes: [] }];
        }
        return [];
      },
    }));

    renderWithProviders(<SchedulesPage />);
    expect(await screen.findByTestId("schedule-row-42")).toBeInTheDocument();
  });
});

describe("TriggersListPage", () => {
  it("renders trigger-row-<id>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => [
        {
          id: 7, name: "RSI cross", enabled: true,
          condition: { all: [] }, last_fired_at: null,
          firings_count: 3,
        },
      ],
    }));

    renderWithProviders(<TriggersListPage />);
    expect(await screen.findByTestId("trigger-row-7")).toBeInTheDocument();
  });
});

describe("ThreadsPage", () => {
  it("renders thread-row-<id>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 55, title: "Morning consult", kind: "consult",
            profile: { name: "Day trader" },
            created_at: "2026-04-17T09:00:00Z",
            message_count: 3,
          },
        ],
      }),
    }));

    renderWithProviders(<ThreadsPage />);
    expect(await screen.findByTestId("thread-row-55")).toBeInTheDocument();
  });
});

describe("WatchlistsList", () => {
  it("renders watchlist-row-<name>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => [{ id: 1, name: "Tech", symbols: [{ ticker: "AAPL" }] }],
    }));

    renderWithProviders(<WatchlistsList />);
    expect(await screen.findByTestId("watchlist-row-Tech")).toBeInTheDocument();
  });
});

describe("ProfilesPage", () => {
  it("renders profile-row-<name>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => [
        {
          id: 2, name: "Swing", style: "swing trading",
          default_includes: ["quotes"], default_provider: "claude",
          default_model: "claude-sonnet-4-6",
        },
      ],
    }));

    renderWithProviders(<ProfilesPage />);
    expect(await screen.findByTestId("profile-row-Swing")).toBeInTheDocument();
  });
});

describe("BackupsPage", () => {
  it("renders backup-row-<id>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => [
        {
          id: 11, status: "ok", kind: "scheduled",
          filename: "backup_11.dump",
          size_bytes: 1024 * 500,
          created_at: "2026-04-17T02:30:00Z",
          error: null,
        },
      ],
    }));

    renderWithProviders(<BackupsPage />);
    expect(await screen.findByTestId("backup-row-11")).toBeInTheDocument();
  });
});

describe("ExportPage", () => {
  it("renders export-row-<id>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => [
        {
          id: 3, status: "done", size_bytes: 2048,
          filename: "export_3.zip",
          created_at: "2026-04-17T10:00:00Z",
          scope: {},
          error: null,
        },
      ],
    }));

    renderWithProviders(<ExportPage />);
    expect(await screen.findByTestId("export-row-3")).toBeInTheDocument();
  });
});

describe("AnalyticsPage", () => {
  it("renders analytics-card-leaderboard", async () => {
    mockFetch(() => ({ ok: true, json: async () => ({}) }));

    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-leaderboard")).toBeInTheDocument();
  });

  it("renders analytics-card-cpi", async () => {
    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-cpi")).toBeInTheDocument();
  });

  it("renders analytics-card-heatmap", async () => {
    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-heatmap")).toBeInTheDocument();
  });

  it("renders analytics-card-timeline", async () => {
    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-timeline")).toBeInTheDocument();
  });

  it("renders analytics-card-unusual-options", async () => {
    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-unusual-options")).toBeInTheDocument();
  });
});

describe("SnapshotComposerPage", () => {
  it("renders capture-btn", async () => {
    mockFetch((url) => ({
      ok: true,
      json: async () => {
        if (url.includes("/api/profiles/")) {
          return [
            { id: 1, name: "P", default_includes: ["quotes"], default_provider: "claude", default_model: "claude-sonnet-4-6" },
          ];
        }
        if (url.includes("/api/watchlists/")) {
          return [{ id: 1, name: "Tech", symbols: [] }];
        }
        return [];
      },
    }));

    // SnapshotComposerPage uses useSnapshotProgress → useChannel → WebSocket
    // context; renderWithProviders supplies WebSocketProvider (socket faked above).
    renderWithProviders(<SnapshotComposerPage />);
    expect(await screen.findByTestId("capture-btn")).toBeInTheDocument();
  });
});

describe("ThreadDetailPage", () => {
  it("renders compose-input", async () => {
    mockFetch((url) => ({
      ok: true,
      json: async () => {
        if (url.includes("/api/threads/")) {
          return {
            id: 1, title: "Test thread", kind: "consult",
            profile: { id: 1, name: "P" },
            messages: [
              {
                id: 100, role: "user", status: "done",
                content: { text: "Hello" }, ai_run: null, error: null,
              },
            ],
            created_at: "2026-04-17T09:00:00Z",
          };
        }
        if (url.includes("/api/files/")) return [];
        return {};
      },
    }));

    // ThreadDetailPage uses useParams + useChannel (WebSocket) — route param
    // comes from routePath, WebSocketProvider from renderWithProviders.
    renderWithProviders(<ThreadDetailPage />, {
      initialEntries: ["/threads/1"],
      routePath: "/threads/:id",
    });
    expect(await screen.findByTestId("compose-input")).toBeInTheDocument();
  });

  it("renders message-<id> for each message", async () => {
    mockFetch((url) => ({
      ok: true,
      json: async () => {
        if (url.includes("/api/threads/")) {
          return {
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
          };
        }
        if (url.includes("/api/files/")) return [];
        return {};
      },
    }));

    renderWithProviders(<ThreadDetailPage />, {
      initialEntries: ["/threads/1"],
      routePath: "/threads/:id",
    });
    expect(await screen.findByTestId("message-100")).toBeInTheDocument();
    expect(screen.getByTestId("message-101")).toBeInTheDocument();
  });
});

describe("BranchTabs", () => {
  it("renders branch-cost-<id> when cost is set", async () => {
    renderWithProviders(
      <BranchTabs
        branches={[{ id: 9, label: "claude/sonnet", status: "done", cost: 0.0012 }]}
        activeId={9}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByTestId("branch-cost-9")).toBeInTheDocument();
  });
});

describe("Citation", () => {
  it("renders citation-<index>", async () => {
    renderWithProviders(<Citation index={3} source="https://example.com" title="Example" />);
    expect(screen.getByTestId("citation-3")).toBeInTheDocument();
  });
});

describe("FileAttachPanel", () => {
  it("renders file-row-<id>", async () => {
    renderWithProviders(
      <FileAttachPanel
        threadId={1}
        files={[
          { id: 22, filename: "report.pdf", kind: "document", ticker: "", mime: "application/pdf", size: 1024 },
        ]}
        onAttach={() => undefined}
      />,
    );
    expect(screen.getByTestId("file-row-22")).toBeInTheDocument();
  });
});

describe("DailyCostChart", () => {
  it("renders cost-tile-today wrapper", async () => {
    render(
      <DailyCostChart
        data={[{ date: "2026-04-17", cost_usd: "1.23", runs: 5 }]}
      />,
    );
    expect(screen.getByTestId("cost-tile-today")).toBeInTheDocument();
  });
});
