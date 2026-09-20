import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { EvalRun } from "@/api/aieval";

const mockRuns = vi.fn();
const mockTrigger = vi.fn();
const mockPush = vi.fn();

vi.mock("@/hooks/useAieval", () => ({
  useEvalRuns: () => mockRuns(),
  useTriggerEvalRun: () => ({ mutateAsync: mockTrigger, isPending: false }),
}));
vi.mock("@/hooks/useAiModels", () => ({
  useAiModels: () => ({
    data: {
      models: [
        { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
          input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5,
          context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
        { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
          input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4,
          context_window: 1_050_000, supports_vision: true, max_payload_tokens: 300_000 },
      ],
      defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" },
    },
    isLoading: false,
  }),
}));
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: mockPush }) }));

import EvalSection from "@/pages/scorecard/EvalSection";

const RUN = (o: Partial<EvalRun> = {}): EvalRun => ({
  id: 1,
  created_at: "2026-09-01T00:00:00Z",
  source: "manual",
  label: "ab",
  provider: "openai",
  model: "gpt-5.6-sol",
  horizon: 30,
  n: 10,
  skipped: 0,
  scored: 10,
  hit_rate: 0.6,
  brier: 0.21,
  avg_confidence: 0.7,
  calibration_error: 0.1,
  calibration: [
    { bin_low: 0.7, bin_high: 0.9, n: 8, hits: 5, observed_hit_rate: 0.625, mean_confidence: 0.8 },
  ],
  ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockRuns.mockReturnValue({ data: [], isLoading: false });
});

describe("EvalSection — run history", () => {
  it("lists every run with its provider and selects the latest by default", () => {
    const claudeRun = RUN({ id: 2, provider: "claude", model: "claude-opus-5", hit_rate: 0.7 });
    mockRuns.mockReturnValue({ data: [claudeRun, RUN()], isLoading: false });
    render(<EvalSection latest={claudeRun} />);

    expect(screen.getAllByTestId("ai-attribution")).toHaveLength(2);
    expect(screen.getByTestId("eval-run-1")).toBeInTheDocument();
    expect(screen.getByTestId("eval-run-2")).toBeInTheDocument();
    // The calibration table describes the selected (latest) run.
    expect(screen.getByText(/How often claude-opus-5's directional call/)).toBeInTheDocument();
  });

  it("switches the calibration table to the run the user picks", async () => {
    const claudeRun = RUN({ id: 2, provider: "claude", model: "claude-opus-5" });
    mockRuns.mockReturnValue({ data: [claudeRun, RUN()], isLoading: false });
    render(<EvalSection latest={claudeRun} />);

    const row = screen.getByTestId("eval-run-1");
    await userEvent.click(row.querySelector("button")!);
    expect(screen.getByText(/How often gpt-5.6-sol's directional call/)).toBeInTheDocument();
  });

  it("offers an empty state rather than a blank table", () => {
    render(<EvalSection latest={undefined} />);
    expect(screen.getByText(/No eval runs yet/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while the history loads", () => {
    mockRuns.mockReturnValue({ data: undefined, isLoading: true });
    render(<EvalSection latest={undefined} />);
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });
});

describe("EvalSection — queueing a run", () => {
  it("queues the chosen target and warns what it will spend", async () => {
    mockTrigger.mockResolvedValue({ queued: true });
    render(<EvalSection latest={undefined} />);

    await userEvent.click(screen.getByRole("button", { name: /run eval/i }));
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "openai");
    expect(screen.getByText(/Makes up to 25 billed calls on OpenAI/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^queue eval$/i }));
    await waitFor(() =>
      expect(mockTrigger).toHaveBeenCalledWith({
        provider: "openai",
        model: "gpt-5.6-sol",
        horizon: 30,
        limit: 25,
        label: "manual",
      }),
    );
    expect(mockPush).toHaveBeenCalledWith(expect.objectContaining({ kind: "success" }));
  });

  it("surfaces a refused run instead of pretending it queued", async () => {
    mockTrigger.mockRejectedValue(new Error("daily cap hit"));
    render(<EvalSection latest={undefined} />);

    await userEvent.click(screen.getByRole("button", { name: /run eval/i }));
    await userEvent.click(screen.getByRole("button", { name: /^queue eval$/i }));
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith({ kind: "error", text: "daily cap hit" }),
    );
  });
});
