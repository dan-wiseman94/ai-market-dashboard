import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "./testUtils";
import SystemSettings from "@/pages/settings/SystemSettings";
import { updateSystemSettings } from "@/api/settings";

const mockUseSystemSettings = vi.fn();
vi.mock("@/hooks/useSystemSettings", () => ({
  useSystemSettings: () => mockUseSystemSettings(),
}));
vi.mock("@/api/settings", () => ({
  updateSystemSettings: vi.fn(async () => ({})),
}));
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }));
vi.mock("@/hooks/useAiModels", () => ({
  useAiModels: () => ({
    data: {
      models: [
        { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
          input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5,
          context_window: 1000000, supports_vision: true, max_payload_tokens: 150000 },
        { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
          input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4,
          context_window: 1050000, supports_vision: true, max_payload_tokens: 300000 },
      ],
      defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" },
    },
    isLoading: false,
  }),
}));

const DEFAULTS = {
  retention_ohlc_days: 400,
  retention_chain_days: 120,
  retention_notification_days: 90,
  retention_error_days: 90,
  retention_regime_days: 180,
  retention_desk_days: 180,
  retention_book_days: 365,
  ai_failover_enabled: false,
  ai_failover_provider: "",
  observer_response_cache_enabled: false,
  observer_response_cache_ttl_seconds: 1800,
  aieval_scheduled_enabled: false,
  aieval_scheduled_provider: "claude",
  aieval_scheduled_model: "claude-opus-5",
  aieval_scheduled_horizon: 30,
  aieval_scheduled_limit: 25,
};

function renderPage() {
  return renderWithProviders(<SystemSettings />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSystemSettings.mockReturnValue({ data: { ...DEFAULTS }, isLoading: false });
});

describe("SystemSettings", () => {
  it("renders effective values and disables Save with no changes", () => {
    renderPage();
    expect(screen.getByLabelText(/OHLC bars/i)).toHaveValue(400);
    expect(screen.getByRole("button", { name: /save changes/i })).toBeDisabled();
  });

  it("shows skeleton rows before data arrives", () => {
    mockUseSystemSettings.mockReturnValue({ data: undefined, isLoading: true });
    renderPage();
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });

  it("PATCHes only the changed fields and toasts on save", async () => {
    renderPage();
    const ohlc = screen.getByLabelText(/OHLC bars/i);
    await userEvent.clear(ohlc);
    await userEvent.type(ohlc, "200");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ retention_ohlc_days: 200 });
    expect(await screen.findByText(/settings saved/i)).toBeInTheDocument();
  });
});

describe("SystemSettings — provider knobs", () => {
  it("picks the failover provider from a list instead of free text", async () => {
    renderPage();
    const select = screen.getByLabelText("Failover provider");
    expect(select.tagName).toBe("SELECT");
    await userEvent.selectOptions(select, "openai");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ ai_failover_provider: "openai" });
  });

  it("carries the eval model with the eval provider so no foreign id is saved", async () => {
    renderPage();
    await userEvent.selectOptions(screen.getByLabelText("Eval provider"), "openai");
    expect(screen.getByLabelText("Eval model")).toHaveValue("gpt-5.6-sol");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({
      aieval_scheduled_provider: "openai",
      aieval_scheduled_model: "gpt-5.6-sol",
    });
  });

  it("offers the post-mortem horizons rather than a free number", async () => {
    renderPage();
    const horizon = screen.getByLabelText("Horizon (days)");
    expect(horizon.tagName).toBe("SELECT");
    await userEvent.selectOptions(horizon, "90");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ aieval_scheduled_horizon: 90 });
  });
});
