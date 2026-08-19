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
  aieval_scheduled_model: "claude-sonnet-4-6",
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
