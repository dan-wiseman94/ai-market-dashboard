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
import TriggersListPage from "../../pages/TriggersListPage";
import ThreadsPage from "../../pages/ThreadsPage";
import WatchlistsList from "../../pages/WatchlistsList";
import ProfilesPage from "../../pages/ProfilesPage";
import ExportPage from "../../pages/ExportPage";
import AnalyticsPage from "../../pages/AnalyticsPage";
import ThreadDetailPage from "../../pages/ThreadDetailPage";
import BranchTabs from "../../components/BranchTabs";
import { FileAttachPanel } from "../../components/FileAttachPanel";
import DailyCostChart from "../../components/costs/DailyCostChart";

// Stub WebSocket so components that open sockets don't throw.
beforeEach(() => {
  installFakeWebSocket();
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
      json: async () => [{ id: 1, name: "Tech", tickers: [{ ticker: "AAPL" }] }],
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

describe("ExportPage", () => {
  it("renders export-row-<id>", async () => {
    mockFetch(() => ({
      ok: true,
      json: async () => ({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 3, status: "done", size_bytes: 2048,
            filename: "export_3.zip",
            created_at: "2026-04-17T10:00:00Z",
            scope: {},
            error: null,
          },
        ],
      }),
    }));

    renderWithProviders(<ExportPage />);
    expect(await screen.findByTestId("export-row-3")).toBeInTheDocument();
  });
});

describe("AnalyticsPage", () => {

  it("renders analytics-card-heatmap", async () => {
    renderWithProviders(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-heatmap")).toBeInTheDocument();
  });
});

describe("ThreadDetailPage", () => {

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
