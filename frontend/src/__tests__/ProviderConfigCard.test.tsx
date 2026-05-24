import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProviderConfigCard from "@/components/ProviderConfigCard";
import type { ProviderConfig } from "@/api/ai";

const mockMutate = vi.fn();
const mockUseProviderConfigs = vi.fn();
const mockUseAiUsage = vi.fn();

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => mockUseProviderConfigs(),
  useUpsertProviderConfig: () => ({ mutate: mockMutate }),
}));

vi.mock("@/hooks/useAiUsage", () => ({
  useAiUsage: () => mockUseAiUsage(),
}));

function makeConfig(overrides: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    provider: "claude",
    base_url: "",
    default_model: "claude-sonnet-4-6",
    enabled: true,
    supports_vision: true,
    daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: null,
    api_key_present: false,
    ...overrides,
  };
}

const defaultConfigs: ProviderConfig[] = [
  makeConfig({ provider: "claude", api_key_present: true }),
  makeConfig({ provider: "openai", api_key_present: false }),
  makeConfig({ provider: "local", api_key_present: false }),
];

const defaultUsage = {
  today: { claude: "0.0012", openai: "0.0000", local: "0" },
};

beforeEach(() => {
  mockUseProviderConfigs.mockReturnValue({ data: defaultConfigs });
  mockUseAiUsage.mockReturnValue({ data: defaultUsage });
  mockMutate.mockReset();
});

describe("ProviderConfigCard", () => {
  it("renders 3 provider sections: claude, openai, local", () => {
    render(<ProviderConfigCard />);
    expect(screen.getByText(/claude/i)).toBeInTheDocument();
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
    expect(screen.getByText(/local/i)).toBeInTheDocument();
  });

  it("shows 'key: ●●●●' for providers with api_key_present, 'no key' otherwise", () => {
    render(<ProviderConfigCard />);
    // claude has api_key_present: true
    expect(screen.getByText("key: ●●●●")).toBeInTheDocument();
    // openai and local have api_key_present: false — should get "no key" (×2)
    const noKey = screen.getAllByText("no key");
    expect(noKey.length).toBeGreaterThanOrEqual(2);
  });

  it("renders today's spend for each provider", () => {
    render(<ProviderConfigCard />);
    expect(screen.getByText("today: $0.0012")).toBeInTheDocument();
    // openai and local both have $0.0000 — two occurrences
    const zeroes = screen.getAllByText("today: $0.0000");
    expect(zeroes.length).toBe(2);
  });

  it("typing in the api_key input updates the field value", async () => {
    const user = userEvent.setup();
    render(<ProviderConfigCard />);
    // Get the first password input (claude's api_key field)
    const apiKeyInputs = screen.getAllByPlaceholderText("API key (leave blank to keep)");
    await user.type(apiKeyInputs[0], "sk-test-key");
    expect(apiKeyInputs[0]).toHaveValue("sk-test-key");
  });

  it("base URL input is only shown for local, not for claude or openai", () => {
    render(<ProviderConfigCard />);
    const baseUrlInputs = screen.getAllByPlaceholderText(/Base URL/i);
    expect(baseUrlInputs.length).toBe(1);
  });

  it("submitting form calls mutate with provider and body; blank monthly_cost_cap_usd becomes null", async () => {
    const user = userEvent.setup();
    render(<ProviderConfigCard />);
    // Get claude's api_key input and type a key
    const apiKeyInputs = screen.getAllByPlaceholderText("API key (leave blank to keep)");
    await user.type(apiKeyInputs[0], "my-api-key");
    // Submit the first (claude) form
    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    await user.click(saveButtons[0]);
    expect(mockMutate).toHaveBeenCalledTimes(1);
    const [callArg] = mockMutate.mock.calls[0];
    expect(callArg.provider).toBe("claude");
    expect(callArg.body.api_key_write).toBe("my-api-key");
    // monthly_cost_cap_usd was blank → null
    expect(callArg.body.monthly_cost_cap_usd).toBeNull();
  });

  it("invoking onSuccess clears the api_key draft for that provider", async () => {
    const user = userEvent.setup();
    render(<ProviderConfigCard />);
    const apiKeyInputs = screen.getAllByPlaceholderText("API key (leave blank to keep)");
    await user.type(apiKeyInputs[0], "temp-key");
    expect(apiKeyInputs[0]).toHaveValue("temp-key");

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    await user.click(saveButtons[0]);

    // Extract the onSuccess callback from the second arg to mutate and invoke it inside act
    const [, options] = mockMutate.mock.calls[0];
    await act(async () => { options.onSuccess(); });

    // After onSuccess fires the draft for claude clears — api_key input becomes empty
    expect(screen.getAllByPlaceholderText("API key (leave blank to keep)")[0]).toHaveValue("");
  });

  it("non-blank monthly_cost_cap_usd is passed through as a string", async () => {
    const user = userEvent.setup();
    render(<ProviderConfigCard />);
    // Find the monthly cap input for claude (first occurrence)
    const monthlyInputs = screen.getAllByPlaceholderText(/Monthly cap USD/i);
    await user.type(monthlyInputs[0], "100.00");
    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    fireEvent.click(saveButtons[0]);
    const [callArg] = mockMutate.mock.calls[0];
    expect(callArg.body.monthly_cost_cap_usd).toBe("100.00");
  });
});
