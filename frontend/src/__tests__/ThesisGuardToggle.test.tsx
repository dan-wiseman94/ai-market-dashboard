import { describe, expect, it, afterEach, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import ThesisDetailPage from "../pages/ThesisDetailPage";
import { mockApi, renderWithProviders } from "./testUtils";
import type { PostMortem } from "@/api/thesis";

// Stub ThesisChart so these page-level tests don't need to mock the OHLC endpoint.
vi.mock("@/components/ThesisChart", () => ({
  default: ({ ticker }: { ticker: string }) => (
    <div data-testid="thesis-chart-stub" data-ticker={ticker} />
  ),
}));

const BASE_THESIS = {
  id: 1,
  title: "NVDA thesis",
  ticker: "NVDA",
  direction: "bullish" as const,
  rationale: "AI boom",
  conviction: 4,
  entry_price: "800.00",
  target_price: "1000.00",
  invalidation_price: "700.00",
  horizon_days: 60,
  status: "open" as const,
  profile_id: 1,
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

afterEach(() => {
  // No global state to clean up; mockApi restores via the returned object.
});

describe("ThesisGuardToggle", () => {
  it("renders the Price guard toggle", async () => {
    mockApi({ "GET /api/theses/1/": BASE_THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByText(/Price guard/i)).toBeInTheDocument());
    expect(screen.getByRole("switch", { name: /price guard/i })).toBeInTheDocument();
  });

  it("toggle is enabled when target_price is set and profile is attached", async () => {
    mockApi({ "GET /api/theses/1/": BASE_THESIS });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: /price guard/i })).toBeInTheDocument());
    expect(screen.getByRole("switch", { name: /price guard/i })).not.toBeDisabled();
  });

  it("toggle is disabled when both target_price and invalidation_price are null", async () => {
    const noPrices = {
      ...BASE_THESIS,
      target_price: null,
      invalidation_price: null,
    };
    mockApi({ "GET /api/theses/1/": noPrices });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: /price guard/i })).toBeInTheDocument());
    expect(screen.getByRole("switch", { name: /price guard/i })).toBeDisabled();
  });

  it("toggle is disabled when profile_id is null", async () => {
    const noProfile = { ...BASE_THESIS, profile_id: null };
    mockApi({ "GET /api/theses/1/": noProfile });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: /price guard/i })).toBeInTheDocument());
    expect(screen.getByRole("switch", { name: /price guard/i })).toBeDisabled();
  });

  it("clicking the toggle PATCHes guard_enabled to the API", async () => {
    const { calls } = mockApi({
      "GET /api/theses/1/": BASE_THESIS,
      "PATCH /api/theses/1/": { ...BASE_THESIS, guard_enabled: true },
    });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: /price guard/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("switch", { name: /price guard/i }));

    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "PATCH" && c.url.includes("/api/theses/1/") && (c.body as Record<string, unknown>)?.guard_enabled === true,
        ),
      ).toBe(true),
    );
  });

  it("shows linked guard trigger link when guard_trigger_id is set", async () => {
    const withGuard = { ...BASE_THESIS, guard_enabled: true, guard_trigger_id: 42 };
    mockApi({ "GET /api/theses/1/": withGuard });
    renderWithProviders(<ThesisDetailPage />, {
      initialEntries: ["/theses/1"],
      routePath: "/theses/:id",
    });
    await waitFor(() => expect(screen.getByTestId("guard-trigger-link")).toBeInTheDocument());
    expect(screen.getByTestId("guard-trigger-link")).toHaveTextContent("#42");
  });
});
