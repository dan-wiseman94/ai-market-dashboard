import { screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvalRunPanel } from "@/components/analytics/EvalRunPanel";
import { mockApi, renderWithProviders, type FetchMock } from "../testUtils";

const SETTINGS = {
  aieval_scheduled_model: "claude-sonnet-4-6",
  aieval_scheduled_horizon: 90,
  aieval_scheduled_limit: 12,
};

const QUEUED = {
  task_id: "abc-123",
  status: "queued",
  provider: "claude",
  model: "claude-sonnet-4-6",
  horizon: 90,
  limit: 12,
  label: "manual",
  system: null,
};

const RUN_ROW = {
  id: 7,
  created_at: "2026-05-01T00:00:00Z",
  source: "manual",
  label: "manual",
  provider: "claude",
  model: "claude-sonnet-4-6",
  horizon: 30,
  n: 10,
  skipped: 0,
  scored: 9,
  hit_rate: 0.55,
  brier: 0.22,
  avg_confidence: 0.7,
  calibration_error: 0.1,
  calibration: [],
};

function setup(overrides: Parameters<typeof mockApi>[0] = {}): FetchMock {
  return mockApi({
    "GET /api/settings/": SETTINGS,
    "GET /api/aieval/runs/": [],
    ...overrides,
  });
}

/** Walk the confirm step: open it, then press the affirmative button. */
async function confirmRun() {
  fireEvent.click(await screen.findByRole("button", { name: /run eval/i }));
  fireEvent.click(screen.getByRole("button", { name: /spend money/i }));
}

describe("EvalRunPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("states up front that a run costs real money", async () => {
    setup();
    renderWithProviders(<EvalRunPanel />);
    expect(await screen.findByText(/spends real money/i)).toBeInTheDocument();
  });

  it("pulls its defaults from the scheduled-eval settings", async () => {
    setup();
    renderWithProviders(<EvalRunPanel />);

    await waitFor(() =>
      expect(screen.getByLabelText(/model/i)).toHaveValue("claude-sonnet-4-6"),
    );
    expect(screen.getByLabelText(/horizon/i)).toHaveValue("90");
    expect(screen.getByLabelText(/snapshots/i)).toHaveValue(12);
  });

  it("does not POST until the cost confirmation is accepted", async () => {
    const fetchMock = setup({ "POST /api/aieval/runs/": QUEUED });
    renderWithProviders(<EvalRunPanel />);

    fireEvent.click(await screen.findByRole("button", { name: /run eval/i }));
    expect(screen.getByTestId("eval-run-confirm")).toHaveTextContent(/costs real money/i);
    expect(fetchMock.calls.filter((c) => c.method === "POST")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByTestId("eval-run-confirm")).not.toBeInTheDocument();
    expect(fetchMock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("posts the resolved parameters and reports the run as queued, not finished", async () => {
    const fetchMock = setup({ "POST /api/aieval/runs/": QUEUED });
    renderWithProviders(<EvalRunPanel />);
    await waitFor(() =>
      expect(screen.getByLabelText(/model/i)).toHaveValue("claude-sonnet-4-6"),
    );

    await confirmRun();

    const banner = await screen.findByTestId("eval-run-queued");
    expect(banner).toHaveTextContent("abc-123");
    expect(banner).toHaveTextContent(/queued is not finished/i);

    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({
      provider: "claude",
      horizon: 90,
      limit: 12,
      model: "claude-sonnet-4-6",
    });
  });

  it('sends horizon null when "every horizon" is picked', async () => {
    const fetchMock = setup({ "POST /api/aieval/runs/": { ...QUEUED, horizon: null } });
    renderWithProviders(<EvalRunPanel />);
    await waitFor(() =>
      expect(screen.getByLabelText(/model/i)).toHaveValue("claude-sonnet-4-6"),
    );

    fireEvent.change(screen.getByLabelText(/horizon/i), { target: { value: "all" } });
    await confirmRun();

    await screen.findByTestId("eval-run-queued");
    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect((post?.body as { horizon: number | null }).horizon).toBeNull();
  });

  it("explains a 409 as mock mode refusing to fabricate a measurement", async () => {
    setup({
      "POST /api/aieval/runs/": {
        status: 409,
        message: "eval runs are unavailable in MOCK_EXTERNAL mode",
      },
    });
    renderWithProviders(<EvalRunPanel />);
    await confirmRun();

    const refusal = await screen.findByTestId("eval-run-refusal");
    expect(refusal).toHaveTextContent(/mock mode/i);
    expect(refusal).toHaveTextContent(/nothing was billed/i);
    expect(screen.queryByTestId("eval-run-queued")).not.toBeInTheDocument();
  });

  it("explains a 429 as the monthly cost cap, distinct from the mock-mode refusal", async () => {
    setup({
      "POST /api/aieval/runs/": { status: 429, message: "monthly cap of $50.00 reached" },
    });
    renderWithProviders(<EvalRunPanel />);
    await confirmRun();

    const refusal = await screen.findByTestId("eval-run-refusal");
    expect(refusal).toHaveTextContent(/cost cap for claude is already reached/i);
    expect(refusal).toHaveTextContent(/monthly cap of \$50\.00 reached/);
    expect(refusal).not.toHaveTextContent(/mock mode/i);
  });

  it("refuses to submit a local run with no model, since there is no catalog default", async () => {
    setup({ "GET /api/settings/": { ...SETTINGS, aieval_scheduled_model: "" } });
    renderWithProviders(<EvalRunPanel />);

    fireEvent.change(await screen.findByLabelText(/provider/i), { target: { value: "local" } });
    expect(screen.getByRole("button", { name: /run eval/i })).toBeDisabled();
    expect(screen.getByText(/name the model first/i)).toBeInTheDocument();
  });

  it("lists recent eval runs, and says so when there are none", async () => {
    setup();
    const { unmount } = renderWithProviders(<EvalRunPanel />);
    expect(await screen.findByText(/no eval runs yet/i)).toBeInTheDocument();
    unmount();

    setup({ "GET /api/aieval/runs/": [RUN_ROW] });
    renderWithProviders(<EvalRunPanel />);
    expect(await screen.findByText("claude-sonnet-4-6")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "55%" })).toBeInTheDocument();
  });
});
