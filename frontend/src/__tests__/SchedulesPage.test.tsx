import { describe, it, expect } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { mockApi, renderWithProviders } from "./testUtils";
import SchedulesPage from "../pages/SchedulesPage";

const SCHEDULES = [
  {
    id: 1, name: "Hourly", profile: 1, enabled: true, market_hours_only: true,
    objective_template: "", override_provider: "", override_model: "",
    default_includes: [], default_watchlist_tickers: [],
    last_fired_at: null, cron_display: "0 * * * *",
    created_at: "2026-04-17T00:00:00Z", updated_at: "2026-04-17T00:00:00Z",
  },
];

const PROFILES = [{ id: 1, name: "P", default_includes: [] }];

describe("SchedulesPage", () => {
  it("renders schedules list", async () => {
    mockApi({
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    expect(screen.getByText(/0 \* \* \* \*/)).toBeInTheDocument();
  });

  it("renders empty state when no schedules", async () => {
    mockApi({
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": [],
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
  });

  it("submits selected preset cron via create form", async () => {
    const mock = mockApi({
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": PROFILES,
      "POST /api/observer/schedules/": {},
    });

    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "TestSched" } });
    // Default preset is "Every 15 minutes"
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "POST")).toBe(true));
    const body = mock.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body.name).toBe("TestSched");
    expect(body.cron).toBe("*/15 * * * *");
    expect(body.profile).toBe(1);
  });
});
