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
    enabled: true, supports_vision: true, supports_tools: true,
    daily_cost_cap_usd: "10.00",
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
    { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
      input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1000000, supports_vision: true,
      max_payload_tokens: 150000 },
    { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
      input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4, context_window: 1050000, supports_vision: true,
      max_payload_tokens: 300000 },
  ], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" } } });
});

describe("ProviderCard — catalog default, capabilities and discovery", () => {
  it("falls back to the catalog's own default when no model is stored", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ default_model: "" })] });
    render(<ProviderCard provider="claude" />);
    expect(screen.getByRole("combobox", { name: "Default model" })).toHaveValue("claude-opus-5");
    expect(screen.getByText(/doesn't name a model/i)).toBeInTheDocument();
  });

  it("shows the selected model's prices and payload budget", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ default_model: "claude-opus-5" })] });
    render(<ProviderCard provider="claude" />);
    const facts = screen.getByTestId("model-facts").textContent ?? "";
    expect(facts).toContain("$5.00 in");
    expect(facts).toContain("150k payload");
  });

  // A save sends BOTH capability flags, the touched one and the untouched one at
  // its displayed (stored) value — the switches show a value resolved in this card,
  // so persisting only the touched one would leave a first-written row taking its
  // other flag from the model default instead of from what the card showed.
  it("offers tool-use and vision toggles off Claude and saves both flags", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "openai", default_model: "gpt-5.6-sol", supports_tools: true, supports_vision: true })],
    });
    render(<ProviderCard provider="openai" />);
    await userEvent.click(screen.getByRole("switch", { name: "Tool use" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body.supports_tools).toBe(false);
    expect(arg.body.supports_vision).toBe(true);
  });

  it("states Claude's fixed capabilities instead of offering toggles", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.queryByRole("switch", { name: "Tool use" })).not.toBeInTheDocument();
    expect(screen.getByText(/structured output · thinking/i)).toBeInTheDocument();
  });

  it("offers an optional base URL and a connection test for OpenAI", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "openai", default_model: "gpt-5.6-sol", api_key_present: true })],
    });
    render(<ProviderCard provider="openai" />);
    const field = screen.getByLabelText("Base URL (optional)");
    expect(screen.getByRole("button", { name: /test connection/i })).toBeEnabled();
    await userEvent.type(field, "https://proxy.example/v1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body.base_url).toBe("https://proxy.example/v1");
  });

  it("offers no base URL or probe for Claude, which publishes no model list", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.queryByLabelText(/base url/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /test connection/i })).not.toBeInTheDocument();
  });

  it("reports when the model list was last synced", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", default_model: "llama3", base_url: "http://x:11434/v1",
                   discovered_models: ["llama3", "qwen"], models_synced_at: new Date().toISOString() })],
    });
    render(<ProviderCard provider="local" />);
    expect(screen.getByText(/Models synced .* · 2 discovered/)).toBeInTheDocument();
  });
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

describe("ProviderCard — capability flags", () => {
  it("renders the tool-use and vision switches from the stored config", () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "openai", supports_tools: false, supports_vision: true })],
    });
    render(<ProviderCard provider="openai" />);
    expect(screen.getByLabelText("Tool use")).not.toBeChecked();
    expect(screen.getByLabelText("Vision")).toBeChecked();
  });

  it("defaults both switches on when the stored row predates the fields", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [] });
    render(<ProviderCard provider="openai" />);
    expect(screen.getByLabelText("Tool use")).toBeChecked();
    expect(screen.getByLabelText("Vision")).toBeChecked();
  });

  it("says out loud that tool use gates a profile's Tools switch for non-Claude", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ provider: "openai" })] });
    render(<ProviderCard provider="openai" />);
    const hintId = screen.getByLabelText("Tool use").getAttribute("aria-describedby");
    expect(document.getElementById(hintId ?? "")).toHaveTextContent(/Tools switch does nothing/i);
  });

  it("persists both flags on save", async () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ provider: "openai" })] });
    render(<ProviderCard provider="openai" />);
    await userEvent.click(screen.getByLabelText("Tool use"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body).toMatchObject({ supports_tools: false, supports_vision: true });
  });

  it("persists them for the local provider too, alongside the base URL", async () => {
    mockUseProviderConfigs.mockReturnValue({
      data: [cfg({ provider: "local", api_key_present: false, default_model: "llama3",
                   base_url: "http://x:11434/v1", discovered_models: ["llama3"] })],
    });
    render(<ProviderCard provider="local" />);
    await userEvent.click(screen.getByLabelText("Vision"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body).toMatchObject({ base_url: "http://x:11434/v1", supports_vision: false });
  });
});

describe("ProviderCard — monthly cap is uncapped by default", () => {
  it("spells out that a blank monthly box means no cap", () => {
    render(<ProviderCard provider="claude" />);
    const monthly = screen.getByLabelText("Monthly cap (USD)");
    expect(monthly).toHaveValue("");
    expect(monthly).toHaveAttribute("placeholder", "no cap");
    const hintId = monthly.getAttribute("aria-describedby");
    expect(document.getElementById(hintId ?? "")).toHaveTextContent(/No monthly cap/i);
  });

  it("swaps the hint once a monthly cap is entered", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.type(screen.getByLabelText("Monthly cap (USD)"), "50");
    const hintId = screen.getByLabelText("Monthly cap (USD)").getAttribute("aria-describedby");
    expect(document.getElementById(hintId ?? "")).toHaveTextContent(/rolling 30 days/i);
  });

  it("says 'no cap set' in the meters block instead of omitting the row", () => {
    mockUseCostsCaps.mockReturnValue({ data: [
      { provider: "claude", daily: { cap: "10.00", spent: "6.00", pct: 0.6 }, monthly: null },
    ] });
    render(<ProviderCard provider="claude" />);
    expect(screen.getByText(/Monthly — no cap set/i)).toBeInTheDocument();
  });
});
