import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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
  ai_failover_enabled: true,
  ai_failover_provider: "",
  observer_response_cache_enabled: true,
  observer_response_cache_ttl_seconds: 1800,
  aieval_scheduled_enabled: true,
  aieval_scheduled_provider: "claude",
  aieval_scheduled_model: "claude-opus-5",
  aieval_scheduled_horizon: 30,
  aieval_scheduled_limit: 25,
  tradingview_tools_enabled: true,
  ai_calibration_routing_enabled: true,
  calibration_drift_sentinel_enabled: true,
  anomaly_sweep_enabled: true,
  returns_adjust_dividends: false,
  ai_investigation_max_iterations: 8,
  ai_autonomous_daily_cap_usd: 5,
  ai_calibration_routing_min_scored: 5,
  ai_calibration_routing_max_age_days: 30,
  restore_from_ui_enabled: true,
  ai_chat_max_tool_iterations: 12,
};

function renderPage() {
  return renderWithProviders(<SystemSettings />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSystemSettings.mockReturnValue({ data: { ...DEFAULTS }, isLoading: false });
});

afterEach(() => {
  vi.restoreAllMocks();
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
    // 400 -> 200 shortens a retention window, so the purge gate asks first.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    const ohlc = screen.getByLabelText(/OHLC bars/i);
    await userEvent.clear(ohlc);
    await userEvent.type(ohlc, "200");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ retention_ohlc_days: 200 });
    expect(await screen.findByText(/settings saved/i)).toBeInTheDocument();
  });

  it("renders the autonomy, calibration, restore and return-math knobs on by default", () => {
    renderPage();
    expect(screen.getByLabelText(/autonomous daily cap/i)).toHaveValue(5);
    expect(screen.getByLabelText(/chat tool rounds/i)).toHaveValue(12);
    expect(screen.getByLabelText(/min scored calls/i)).toHaveValue(5);
    expect(screen.getByLabelText(/scheduled anomaly sweep/i)).toBeChecked();
    expect(screen.getByLabelText(/route by measured calibration/i)).toBeChecked();
    expect(screen.getByLabelText(/alert on calibration drift/i)).toBeChecked();
    expect(screen.getByLabelText(/allow restore from the ui/i)).toBeChecked();
    expect(screen.getByLabelText(/dividend-adjusted/i)).not.toBeChecked();
  });

  it("PATCHes a newly-disarmed autonomous sweep", async () => {
    // Disarming is free, so it must not ask.
    const confirmSpy = vi.spyOn(window, "confirm");
    renderPage();
    await userEvent.click(screen.getByLabelText(/scheduled anomaly sweep/i));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ anomaly_sweep_enabled: false });
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("PATCHes a fractional autonomous daily cap", async () => {
    renderPage();
    const cap = screen.getByLabelText(/autonomous daily cap/i);
    await userEvent.clear(cap);
    await userEvent.type(cap, "2.5");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({
      ai_autonomous_daily_cap_usd: 2.5,
    });
  });

  it("asks before switching to dividend-adjusted returns and keeps the draft clean on decline", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    await userEvent.click(screen.getByLabelText(/dividend-adjusted/i));
    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.getByLabelText(/dividend-adjusted/i)).not.toBeChecked();
    expect(screen.getByRole("button", { name: /save changes/i })).toBeDisabled();
  });

  it("switches to dividend-adjusted returns once confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await userEvent.click(screen.getByLabelText(/dividend-adjusted/i));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({
      returns_adjust_dividends: true,
    });
  });

  it("exposes each hint as a description, not as part of the control's name", () => {
    renderPage();
    // An exact-name lookup fails if the hint were folded into the label, and an
    // aria-label overriding the name would hide the hint from a screen reader
    // entirely — this pins both.
    const cap = screen.getByLabelText("Autonomous daily cap (USD)");
    const capHint = String(cap.getAttribute("aria-describedby"));
    expect(document.getElementById(capHint)?.textContent).toMatch(/0 removes this ceiling/);

    const sweep = screen.getByLabelText("Scheduled anomaly sweep");
    const sweepHint = String(sweep.getAttribute("aria-describedby"));
    expect(document.getElementById(sweepHint)?.textContent).toMatch(
      /opens Desk investigations on its own/,
    );

    const dividends = screen.getByLabelText("Dividend-adjusted (total-return) math");
    const dividendHint = String(dividends.getAttribute("aria-describedby"));
    expect(document.getElementById(dividendHint)?.textContent).toMatch(/Retroactive/);
  });

  it("leaves hintless controls undescribed rather than pointing at nothing", () => {
    renderPage();
    expect(screen.getByLabelText("OHLC bars (days)")).not.toHaveAttribute("aria-describedby");
  });

  it("asks before arming a background job that bills on a schedule", async () => {
    mockUseSystemSettings.mockReturnValue({
      data: { ...DEFAULTS, anomaly_sweep_enabled: false, aieval_scheduled_enabled: false },
      isLoading: false,
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();

    await userEvent.click(screen.getByLabelText("Scheduled anomaly sweep"));
    expect(String(confirmSpy.mock.calls[0]?.[0])).toMatch(/billed model calls/i);
    expect(screen.getByLabelText("Scheduled anomaly sweep")).not.toBeChecked();

    await userEvent.click(screen.getByLabelText("Enable scheduled eval"));
    expect(String(confirmSpy.mock.calls[1]?.[0])).toMatch(/real, billed model calls/i);
    expect(screen.getByLabelText("Enable scheduled eval")).not.toBeChecked();

    // Nothing was accepted, so there is nothing to save.
    expect(screen.getByRole("button", { name: /save changes/i })).toBeDisabled();
  });

  it("names the rows a shortened retention window will purge, and can be declined", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    const ohlc = screen.getByLabelText("OHLC bars (days)");
    await userEvent.clear(ohlc);
    await userEvent.type(ohlc, "30");

    expect(screen.getByRole("status")).toHaveTextContent(/OHLC bars 400→30/);
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(String(confirmSpy.mock.calls[0]?.[0])).toMatch(/OHLC bars: 400 → 30 days/);
    expect(vi.mocked(updateSystemSettings)).not.toHaveBeenCalled();
  });

  it("does not gate a lengthened retention window", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    renderPage();
    const ohlc = screen.getByLabelText("OHLC bars (days)");
    await userEvent.clear(ohlc);
    await userEvent.type(ohlc, "800");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ retention_ohlc_days: 800 });
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
