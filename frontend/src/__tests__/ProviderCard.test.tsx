import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProviderCard from "@/components/settings/ProviderCard";
import type { ProviderConfig } from "@/api/ai";

const mockMutate = vi.fn();
const mockProbeMutate = vi.fn();
const mockUseProviderConfigs = vi.fn();
const mockUseAiUsage = vi.fn();
const mockUseCostsCaps = vi.fn();
const mockUseAiModels = vi.fn();
const mockPush = vi.fn();

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => mockUseProviderConfigs(),
  useUpsertProviderConfig: () => ({ mutate: mockMutate, isPending: false }),
  useProbeProvider: () => ({ mutate: mockProbeMutate, isPending: false }),
}));
vi.mock("@/hooks/useAiUsage", () => ({ useAiUsage: () => mockUseAiUsage() }));
vi.mock("@/hooks/useCosts", () => ({ useCostsCaps: () => mockUseCostsCaps() }));
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: mockPush }) }));

function cfg(o: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    provider: "claude", base_url: "", default_model: "claude-sonnet-4-6",
    enabled: true, supports_vision: true, daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: null, api_key_present: true,
    discovered_models: [], models_synced_at: null, ...o,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProviderConfigs.mockReturnValue({ data: [cfg()] });
  mockUseAiUsage.mockReturnValue({ data: { today: { claude: "0.4231" } } });
  mockUseCostsCaps.mockReturnValue({ data: [] });
  mockUseAiModels.mockReturnValue({ data: { models: [
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude",
      input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200000, supports_vision: true },
  ] } });
});

describe("ProviderCard", () => {
  it("renders a labeled API key input named '<Provider> API key'", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.getByLabelText("Claude API key")).toBeInTheDocument();
  });

  it("shows a 'key set' indicator and today's spend", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.getByText(/key set/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.4231/)).toBeInTheDocument();
  });

  it("omits api_key_write from the save body when the key field is untouched (bug fix)", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.provider).toBe("claude");
    expect("api_key_write" in arg.body).toBe(false);
  });

  it("includes api_key_write only when a new key was typed", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.type(screen.getByLabelText("Claude API key"), "sk-new");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body.api_key_write).toBe("sk-new");
  });

  it("sends monthly cap as null when blank and clears the draft on success", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.type(screen.getByLabelText("Claude API key"), "sk-temp");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg, opts] = mockMutate.mock.calls[0];
    expect(arg.body.monthly_cost_cap_usd).toBeNull();
    await act(async () => { opts.onSuccess(); });
    expect(screen.getByLabelText("Claude API key")).toHaveValue("");
    expect(mockPush).toHaveBeenCalledWith(expect.objectContaining({ kind: "success" }));
  });

  it("renders the base URL field only for the local provider", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ provider: "local", api_key_present: false })] });
    render(<ProviderCard provider="local" />);
    expect(screen.getByLabelText("Base URL")).toBeInTheDocument();
  });
});

describe("ProviderCard — toggle, meters, validation", () => {
  it("persists the enable toggle immediately", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.click(screen.getByRole("switch", { name: "Claude enabled" }));
    expect(mockMutate).toHaveBeenCalledWith(
      { provider: "claude", body: { enabled: false } },
      expect.any(Object),
    );
  });

  it("renders daily and monthly cap meters from costs-caps", () => {
    mockUseCostsCaps.mockReturnValue({ data: [
      { provider: "claude", daily: { cap: "10.00", spent: "6.00", pct: 0.6 },
        monthly: { cap: "100.00", spent: "20.00", pct: 0.2 } },
    ] });
    render(<ProviderCard provider="claude" />);
    expect(screen.getByText("$6.00 / $10.00")).toBeInTheDocument();
    expect(screen.getByText("$20.00 / $100.00")).toBeInTheDocument();
  });

  it("disables Save when the daily cap is invalid", async () => {
    render(<ProviderCard provider="claude" />);
    const daily = screen.getByLabelText("Daily cap (USD)");
    await userEvent.clear(daily);
    await userEvent.type(daily, "-5");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});

describe("ProviderCard — local provider", () => {
  it("hides the cost caps and shows the no-cost note for local", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    render(<ProviderCard provider="local" />);
    expect(screen.queryByLabelText("Daily cap (USD)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Monthly cap (USD)")).not.toBeInTheDocument();
    expect(screen.getByText(/no API cost/i)).toBeInTheDocument();
  });

  it("auto-probes on mount when base_url is set but no models discovered", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false,
                   base_url: "http://x:11434/v1", discovered_models: [] })],
    });
    render(<ProviderCard provider="local" />);
    expect(mockProbeMutate).toHaveBeenCalledWith(
      { provider: "local", body: {} },
    );
  });

  it("Test connection sends current base_url and shows the result", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    mockProbeMutate.mockImplementation((_args, opts) =>
      opts?.onSuccess?.({ ok: true, models: ["llama3", "mistral"], synced_at: "now" }),
    );
    render(<ProviderCard provider="local" />);
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const call = mockProbeMutate.mock.calls.find((c) => c[1] !== undefined);
    expect(call?.[0]).toEqual({
      provider: "local",
      body: { base_url: "http://x:11434/v1", api_key_write: undefined },
    });
    expect(screen.getByText(/Connected — 2 models found/i)).toBeInTheDocument();
  });

  it("shows the friendly error when the probe reports ok:false", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    mockProbeMutate.mockImplementation((_args, opts) =>
      opts?.onSuccess?.({ ok: false, error: "Couldn't reach http://x:11434/v1." }),
    );
    render(<ProviderCard provider="local" />);
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(screen.getByText(/Couldn't reach/i)).toBeInTheDocument();
  });
});
