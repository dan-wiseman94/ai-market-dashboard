import { screen, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ObserverTodayTile } from "@/components/dashboard/ObserverTodayTile";
import { mockApi, renderWithProviders } from "../testUtils";

const schedule = (over: Record<string, unknown> = {}) => ({
  id: 1, name: "Hourly", profile: 4, enabled: true, market_hours_only: true,
  objective_template: "", override_provider: "", override_model: "",
  default_includes: [], default_watchlist_tickers: [],
  mode: "full", structured: false, use_batch: false, consensus: false,
  investigate: true, fire_mode: "cron", close_offset_minutes: 5,
  last_batch_id: "", last_fired_at: null, cron_display: "0 * * * *",
  created_at: "2026-04-17T00:00:00Z", updated_at: "2026-04-17T00:00:00Z",
  ...over,
});

describe("ObserverTodayTile", () => {
  it("shows runs_today and enabled_schedules counts", async () => {
    mockApi({ "GET /api/observer/schedules/": [] });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 5, enabled_schedules: 3 }} />,
    );
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("5");
    expect(
      screen.getByTestId("observer-enabled-schedules").textContent,
    ).toBe("3");
  });

  it("shows '0 runs today' when there are none", async () => {
    mockApi({ "GET /api/observer/schedules/": [] });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 0, enabled_schedules: 0 }} />,
    );
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("0");
    expect(screen.getByText("runs today")).toBeInTheDocument();
  });

  it("links to /schedules", async () => {
    mockApi({ "GET /api/observer/schedules/": [] });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 2, enabled_schedules: 4 }} />,
    );
    const link = screen.getByRole("link", { name: /^schedules/i });
    expect(link).toHaveAttribute("href", "/schedules");
  });

  it("points the timeline at an armed schedule's own profile, not a hardcoded #1", async () => {
    mockApi({
      "GET /api/observer/schedules/": [
        schedule({ id: 2, profile: 9, enabled: false }),
        schedule({ id: 3, profile: 4, enabled: true }),
      ],
    });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 1, enabled_schedules: 1 }} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("observer-timeline-link"))
        .toHaveAttribute("href", "/threads/observer/4"));
  });

  it("falls back to a disabled schedule's profile when nothing is armed", async () => {
    mockApi({ "GET /api/observer/schedules/": [schedule({ profile: 7, enabled: false })] });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 0, enabled_schedules: 0 }} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("observer-timeline-link"))
        .toHaveAttribute("href", "/threads/observer/7"));
  });

  it("offers schedule creation instead of a dead timeline link when there are no schedules", async () => {
    mockApi({ "GET /api/observer/schedules/": [] });
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 0, enabled_schedules: 0 }} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("observer-timeline-link"))
        .toHaveAttribute("href", "/schedules"));
    expect(screen.getByText(/create a schedule/i)).toBeInTheDocument();
  });
});
