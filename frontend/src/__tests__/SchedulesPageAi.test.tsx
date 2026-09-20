import { describe, it, expect } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderWithProviders } from "./testUtils";
import SchedulesPage from "@/pages/SchedulesPage";

const MODELS = {
  models: [
    { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
      input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5,
      context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
    { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
      input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4,
      context_window: 1_050_000, supports_vision: true, max_payload_tokens: 300_000 },
  ],
  defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" },
};

const PROFILES = [
  {
    id: 1, name: "P", default_includes: [], active: true, style: "",
    default_provider: "claude", default_model: "claude-opus-5",
    enable_tools: false, enable_thinking: false, thinking_budget: 8000,
    enable_memory: false, enable_coach: true,
  },
];

const OVERRIDDEN = {
  id: 1, name: "Hourly", profile: 1, enabled: true, market_hours_only: true,
  objective_template: "", override_provider: "openai", override_model: "gpt-5.6-sol",
  default_includes: [], default_watchlist_tickers: [],
  mode: "full", structured: true, use_batch: false, consensus: false, investigate: false,
  last_batch_id: "", last_fired_at: null, cron_display: "0 * * * *",
  fire_mode: "cron", close_offset_minutes: 5,
  created_at: "2026-04-17T00:00:00Z", updated_at: "2026-04-17T00:00:00Z",
};

const BASE = {
  "GET /api/schwab/providers/": [],
  "GET /api/schwab/models/": MODELS,
  "GET /api/profiles/": PROFILES,
};

describe("SchedulesPage — AI target and mode", () => {
  it("shows a row's effective target and its mode badges", async () => {
    mockApi({ ...BASE, "GET /api/observer/schedules/": [OVERRIDDEN] });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());

    const row = screen.getByTestId("schedule-row-1");
    const pill = within(row).getByTestId("ai-attribution").textContent ?? "";
    expect(pill).toContain("OpenAI · gpt-5.6-sol");
    expect(pill).toContain("(override)");
    expect(within(row).getByTestId("mode-badges").textContent).toContain("structured");
    // One checkbox while the editors are closed — the enabled toggle.
    expect(within(row).getAllByRole("checkbox")).toHaveLength(1);
  });

  it("falls back to the profile's target when the schedule has no override", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [{ ...OVERRIDDEN, override_provider: "", override_model: "" }],
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());

    const pill = within(screen.getByTestId("schedule-row-1")).getByTestId("ai-attribution");
    expect(pill.textContent).toContain("Claude · claude-opus-5");
    expect(pill.textContent).toContain("(profile)");
  });

  it("creates with an inherited target by default and an override when chosen", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "POST /api/observer/schedules/": {},
    });
    const user = userEvent.setup();
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "AB-openai" } });
    expect(screen.getByTestId("sched-new-effective-target").textContent).toBe(
      "Runs on Claude · claude-opus-5 (from profile)",
    );

    await user.selectOptions(screen.getByLabelText("Override provider"), "openai");
    expect(screen.getByTestId("sched-new-effective-target").textContent).toBe(
      "Runs on OpenAI · gpt-5.6-sol (override)",
    );
    fireEvent.click(screen.getByLabelText(/^Structured \(typed/));
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "POST")).toBe(true));
    const body = mock.calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body).toMatchObject({
      name: "AB-openai",
      override_provider: "openai",
      override_model: "gpt-5.6-sol",
      structured: true,
      investigate: false,
      consensus: false,
    });
  });

  it("disables Messages Batch off Claude and Investigate under Structured", async () => {
    mockApi({ ...BASE, "GET /api/observer/schedules/": [] });
    const user = userEvent.setup();
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    expect(screen.getByLabelText(/^Messages Batch/)).toBeEnabled();

    await user.selectOptions(screen.getByLabelText("Override provider"), "openai");
    expect(screen.getByLabelText(/^Messages Batch/)).toBeDisabled();
    expect(screen.getByText(/Claude only — Messages Batches/)).toBeInTheDocument();

    expect(screen.getByLabelText(/^Cross-model consensus/)).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/^Structured \(typed/));
    expect(screen.getByLabelText(/^Cross-model consensus/)).toBeEnabled();
    expect(screen.getByLabelText(/^Investigate/)).toBeDisabled();
  });

  it("edits a row's AI settings and PATCHes them", async () => {
    const mock = mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [OVERRIDDEN],
      "PATCH /api/observer/schedules/1/": {},
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^ai$/i }));
    fireEvent.click(screen.getByLabelText(/^Cross-model consensus/));
    fireEvent.click(screen.getByRole("button", { name: /save ai settings/i }));

    await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
    const body = mock.calls.find((c) => c.method === "PATCH")!.body as Record<string, unknown>;
    expect(body).toMatchObject({
      consensus: true,
      structured: true,
      override_provider: "openai",
      override_model: "gpt-5.6-sol",
      mode: "full",
      use_batch: false,
      investigate: false,
    });
  });

  it("surfaces a rejected create instead of failing silently", async () => {
    mockApi({
      ...BASE,
      "GET /api/observer/schedules/": [],
      "POST /api/observer/schedules/": { status: 400, code: "invalid", message: "nope" },
    });
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "X" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByTestId("toast-error")).toBeInTheDocument();
  });
});
