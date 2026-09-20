import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import ProfilesPage from "@/pages/ProfilesPage";
import type { TradingProfile } from "@/api/profiles";

vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: vi.fn(),
  useCreateProfile: vi.fn(),
  useUpdateProfile: vi.fn(),
  useDeleteProfile: vi.fn(),
}));
vi.mock("@/hooks/useAgentPresets", () => ({
  useAgentPresets: () => ({ data: [] }),
  useCreatePreset: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdatePreset: () => ({ mutate: vi.fn(), isPending: false }),
  useDeletePreset: () => ({ mutate: vi.fn(), isPending: false }),
}));

const AI_MODELS = {
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
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => ({ data: AI_MODELS }) }));

// OpenAI has tool use switched off, so the form must say so when it is selected.
const PROVIDER_CONFIGS = [
  { provider: "claude", base_url: "", default_model: "", enabled: true, supports_vision: true,
    supports_tools: true, daily_cost_cap_usd: "10", monthly_cost_cap_usd: null, api_key_present: true },
  { provider: "openai", base_url: "", default_model: "", enabled: true, supports_vision: true,
    supports_tools: false, daily_cost_cap_usd: "10", monthly_cost_cap_usd: null, api_key_present: true },
];
vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => ({ data: PROVIDER_CONFIGS }),
}));

import {
  useProfiles, useCreateProfile, useUpdateProfile, useDeleteProfile,
} from "@/hooks/useProfiles";

const mockUseProfiles = vi.mocked(useProfiles);
const mockUseCreateProfile = vi.mocked(useCreateProfile);
const mockUseUpdateProfile = vi.mocked(useUpdateProfile);
const mockUseDeleteProfile = vi.mocked(useDeleteProfile);

const PROFILE: TradingProfile = {
  id: 1,
  name: "Swing Trader",
  style: "Hold 2-5 days",
  default_includes: ["quotes", "ohlc"],
  default_provider: "claude",
  default_model: "claude-opus-5",
  active: true,
  enable_tools: false,
  enable_thinking: false,
  thinking_budget: 8000,
  enable_memory: false,
  enable_coach: true,
};

function mutateStub() {
  const m = vi.fn((_args: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  return m;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProfiles.mockReturnValue({ data: [PROFILE] } as never);
  mockUseCreateProfile.mockReturnValue({ mutate: mutateStub(), isPending: false } as never);
  mockUseUpdateProfile.mockReturnValue({ mutate: mutateStub(), isPending: false } as never);
  mockUseDeleteProfile.mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
});

describe("ProfileForm — AI features", () => {
  it("posts the per-profile feature flags and the thinking budget", async () => {
    const mutate = mutateStub();
    mockUseCreateProfile.mockReturnValue({ mutate, isPending: false } as never);
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    await user.type(screen.getByPlaceholderText("Profile name"), "Scalper");
    await user.click(screen.getByRole("switch", { name: "Enable tools" }));
    await user.click(screen.getByRole("switch", { name: "Extended thinking" }));
    const budget = screen.getByLabelText("Thinking budget");
    await user.clear(budget);
    await user.type(budget, "16000");
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        enable_tools: true,
        enable_thinking: true,
        thinking_budget: 16000,
        enable_memory: false,
        enable_coach: true,
      }),
      expect.anything(),
    );
  });

  it("reveals the thinking budget only once extended thinking is on", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    expect(screen.queryByLabelText("Thinking budget")).not.toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "Extended thinking" }));
    expect(screen.getByLabelText("Thinking budget")).toBeInTheDocument();
  });

  it("names the features the selected provider cannot honor", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    expect(screen.queryByText(/Claude only/)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Default provider"), "openai");
    expect(screen.getAllByText("Claude only — ignored on OpenAI")).toHaveLength(2);
    expect(
      screen.getByText("Tool use is off for OpenAI in Settings → AI Providers"),
    ).toBeInTheDocument();
  });

  it("carries the model with the provider so no foreign id is submitted", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    await user.selectOptions(screen.getByLabelText("Default provider"), "openai");
    expect(screen.getByLabelText("Default model")).toHaveValue("gpt-5.6-sol");
  });
});

describe("ProfileList — activation and attribution", () => {
  it("toggles a profile's active flag from its row", async () => {
    const mutate = mutateStub();
    mockUseUpdateProfile.mockReturnValue({ mutate, isPending: false } as never);
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    const row = screen.getByTestId("profile-row-Swing Trader");
    await user.click(within(row).getByRole("button", { name: "Deactivate" }));
    expect(mutate).toHaveBeenCalledWith(
      { id: PROFILE.id, body: { active: false } },
      expect.anything(),
    );
  });

  it("marks an inactive profile and offers to re-activate it", () => {
    mockUseProfiles.mockReturnValue({ data: [{ ...PROFILE, active: false }] } as never);
    renderWithProviders(<ProfilesPage />);
    const row = screen.getByTestId("profile-row-Swing Trader");
    expect(within(row).getByText("Inactive")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Activate" })).toBeInTheDocument();
  });

  it("shows the profile's target and enabled features on its row", () => {
    mockUseProfiles.mockReturnValue({
      data: [{ ...PROFILE, enable_tools: true, enable_memory: true }],
    } as never);
    renderWithProviders(<ProfilesPage />);
    const row = screen.getByTestId("profile-row-Swing Trader");
    expect(within(row).getByTestId("ai-attribution").textContent).toBe("Claude · claude-opus-5");
    expect(within(row).getByText("tools")).toBeInTheDocument();
    expect(within(row).getByText("memory")).toBeInTheDocument();
    expect(within(row).queryByText("thinking")).not.toBeInTheDocument();
  });
});
