import { describe, it, expect } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { mockApi, renderWithProviders } from "./testUtils";
import SchedulesPage from "../pages/SchedulesPage";

const SCHEDULES = [
  {
    id: 1, name: "Hourly", profile: 1, enabled: true, market_hours_only: true,
    objective_template: "", override_provider: "", override_model: "",
    default_includes: [], default_watchlist_tickers: [],
    mode: "full", structured: false, use_batch: false, consensus: false,
    investigate: true, fire_mode: "cron", close_offset_minutes: 5,
    last_batch_id: "", last_fired_at: null, cron_display: "0 * * * *",
    created_at: "2026-04-17T00:00:00Z", updated_at: "2026-04-17T00:00:00Z",
  },
];

const PROFILES = [{ id: 1, name: "P", default_includes: [] }];

const MODELS = {
  models: [
    {
      id: "claude-sonnet-4-6", name: "Sonnet 4.6", provider: "claude",
      input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3,
      context_window: 200000, supports_vision: true,
    },
  ],
  defaults: { claude: "claude-sonnet-4-6", openai: "gpt-5.6-sol", local: "" },
};

// The schedule form's AI fieldset reads the catalog and the provider configs.
const BASE = {
  "GET /api/schwab/models/": MODELS,
  "GET /api/schwab/providers/": [],
};

describe("SchedulesPage", () => {
  it("renders schedules list", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    expect(screen.getByText(/0 \* \* \* \*/)).toBeInTheDocument();
  });

  it("renders empty state when no schedules", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": [],
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
  });

  it("submits selected preset cron via create form", async () => {
    const mock = mockApi({
      ...BASE,
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

  it("opening the sections editor with empty default_includes shows the inherit hint", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^sections$/i }));
    expect(screen.getByText(/inherits the profile's default sections/i)).toBeInTheDocument();
  });

  it("saving the sections editor PATCHes default_includes on the schedule", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
      "PATCH /api/observer/schedules/1/": {},
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^sections$/i }));
    fireEvent.click(screen.getByLabelText("Quotes"));
    fireEvent.click(screen.getByLabelText("News"));
    fireEvent.click(screen.getByRole("button", { name: /save sections/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
    const call = mock.calls.find((c) => c.method === "PATCH")!;
    expect(call.url).toContain("/api/observer/schedules/1/");
    const body = call.body as Record<string, unknown>;
    expect(body.default_includes).toEqual(["quotes", "news"]);
  });

  it("create posts the previously-unreachable fields: investigate, watchlist override, model override", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": PROFILES,
      "POST /api/observer/schedules/": {},
    });

    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Rich" } });

    const tickers = screen.getByLabelText(/watchlist override tickers/i);
    fireEvent.change(tickers, { target: { value: "TSLA" } });
    fireEvent.keyDown(tickers, { key: "Enter" });

    // Wait for the catalog: the picker resolves a provider's model from it, and
    // choosing a provider before it lands would leave the model blank.
    await waitFor(() =>
      expect(screen.getByTestId("sched-new-effective-target").textContent)
        .toContain("claude-sonnet-4-6"));
    fireEvent.change(screen.getByLabelText("Override provider"), { target: { value: "claude" } });
    expect(screen.getByRole("option", { name: "Sonnet 4.6" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(mock.calls.some((c) => c.method === "POST")).toBe(true));

    const body = mock.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body.default_watchlist_tickers).toEqual(["TSLA"]);
    expect(body.override_provider).toBe("claude");
    expect(body.override_model).toBe("claude-sonnet-4-6");
    // Investigate is on by default and must reach the API as such.
    expect(body.investigate).toBe(true);
  });

  it("leaves the provider/model override empty when the target is inherited", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": PROFILES,
      "POST /api/observer/schedules/": {},
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Inherit" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "POST")).toBe(true));
    const body = mock.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body.override_provider).toBe("");
    expect(body.override_model).toBe("");
  });

  it("the investigate control carries the spend warning, not just a checkbox", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "GET /api/profiles/": PROFILES,
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));

    const box = screen.getByLabelText(/investigate \(autonomous tool loop/i);
    expect(box).toBeChecked();
    const describedBy = box.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy)!.textContent)
      .toMatch(/costs materially more per fire/i);
  });

  it("the edit expander seeds from the schedule and PATCHes the create-only fields", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
      "PATCH /api/observer/schedules/1/": {},
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /edit hourly/i }));

    // Seeded from the saved row. (The cron preset select also displays
    // "Hourly", so target the name field by its label.)
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("Hourly");
    expect(screen.getByLabelText(/market hours only/i)).toBeChecked();

    fireEvent.click(screen.getByLabelText(/market hours only/i));
    fireEvent.change(screen.getByLabelText(/payload shape/i), { target: { value: "diff" } });
    fireEvent.click(screen.getByLabelText(/^structured \(typed/i));
    fireEvent.click(screen.getByRole("button", { name: /save schedule/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
    const call = mock.calls.find((c) => c.method === "PATCH")!;
    expect(call.url).toContain("/api/observer/schedules/1/");
    expect(call.body).toMatchObject({
      name: "Hourly",
      profile: 1,
      market_hours_only: false,
      mode: "diff",
      structured: true,
      fire_mode: "cron",
      // The saved cron round-trips through the preset list untouched.
      cron: "0 * * * *",
      // Turning Structured on clears Investigate: a structured fire never runs
      // the tool loop, so sending both would bill for a mode the backend ignores.
      investigate: false,
    });
  });

  it("switching a saved cron schedule to relative-to-close PATCHes the offset", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
      "PATCH /api/observer/schedules/1/": {},
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /edit hourly/i }));
    fireEvent.change(screen.getByLabelText(/fire mode/i), { target: { value: "relative_to_close" } });
    fireEvent.change(screen.getByLabelText(/minutes before close/i), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: /save schedule/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
    const body = mock.calls.find((c) => c.method === "PATCH")!.body as Record<string, unknown>;
    expect(body.fire_mode).toBe("relative_to_close");
    expect(body.close_offset_minutes).toBe(12);
    expect(body.cron).toBeUndefined();
  });

  it("each row links to its own profile's observer timeline", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": SCHEDULES,
      "GET /api/profiles/": PROFILES,
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /timeline/i }))
      .toHaveAttribute("href", "/threads/observer/1");
  });
});
