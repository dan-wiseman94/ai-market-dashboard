// frontend/src/__tests__/ProviderCard.test.tsx
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProviderCard from "@/components/settings/ProviderCard";
import type { ProviderConfig } from "@/api/ai";

const mockMutate = vi.fn();
const mockUseProviderConfigs = vi.fn();
const mockUseAiUsage = vi.fn();
const mockUseCostsCaps = vi.fn();
const mockUseAiModels = vi.fn();
const mockPush = vi.fn();

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => mockUseProviderConfigs(),
  useUpsertProviderConfig: () => ({ mutate: mockMutate, isPending: false }),
}));
vi.mock("@/hooks/useAiUsage", () => ({ useAiUsage: () => mockUseAiUsage() }));
vi.mock("@/hooks/useCosts", () => ({ useCostsCaps: () => mockUseCostsCaps() }));
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: mockPush }) }));

function cfg(o: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    provider: "claude", base_url: "", default_model: "claude-sonnet-4-6",
    enabled: true, supports_vision: true, daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: null, api_key_present: true, ...o,
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
