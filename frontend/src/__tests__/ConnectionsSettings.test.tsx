// frontend/src/__tests__/ConnectionsSettings.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ConnectionsSettings from "@/pages/settings/ConnectionsSettings";
import { fetchSchwabAuthorizeUrl, updateSchwabAppConfig } from "@/api/schwab";
import { ToastProvider } from "@/hooks/useToast";
import { Toasts } from "@/components/Toasts";

const mockUseSchwabStatus = vi.fn();
const mockUseSchwabAppConfig = vi.fn();
vi.mock("@/hooks/useSchwabStatus", () => ({
  useSchwabStatus: () => mockUseSchwabStatus(),
  useSchwabAppConfig: () => mockUseSchwabAppConfig(),
}));
vi.mock("@/api/schwab", () => ({
  fetchSchwabAuthorizeUrl: vi.fn(async () => ({ url: "/x" })),
  updateSchwabAppConfig: vi.fn(async () => ({
    client_id: "APPKEY",
    client_secret_present: true,
    configured: true,
  })),
}));
vi.mock("@/hooks/useCalendarOverrides", () => ({
  useCalendarOverrides: () => ({ data: [] }),
  useCreateCalendarOverride: () => ({ mutate: vi.fn() }),
  useDeleteCalendarOverride: () => ({ mutate: vi.fn() }),
}));

// useToast() / useQueryClient() throw without their providers; AppLayout supplies both in prod.
function renderWithProviders() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ConnectionsSettings />
        <Toasts />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSchwabAppConfig.mockReturnValue({
    data: { client_id: "", client_secret_present: false, configured: true },
  });
});

describe("ConnectionsSettings", () => {
  it("shows not-connected state with a Connect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    renderWithProviders();
    expect(screen.getByText(/not connected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect schwab/i })).toBeInTheDocument();
  });

  it("shows connected state with a Reconnect button", () => {
    mockUseSchwabStatus.mockReturnValue({
      data: { connected: true, expires_at: null },
      isLoading: false,
    });
    renderWithProviders();
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
  });

  it("disables Connect until credentials are configured", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    mockUseSchwabAppConfig.mockReturnValue({
      data: { client_id: "", client_secret_present: false, configured: false },
    });
    renderWithProviders();
    expect(screen.getByRole("button", { name: /connect schwab/i })).toBeDisabled();
  });

  it("saves entered credentials via the app-config API", async () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    renderWithProviders();
    await userEvent.type(screen.getByLabelText(/app key/i), "APPKEY");
    await userEvent.type(screen.getByLabelText(/secret/i), "SECRET");
    await userEvent.click(screen.getByRole("button", { name: /save credentials/i }));
    expect(vi.mocked(updateSchwabAppConfig)).toHaveBeenCalledWith({
      client_id: "APPKEY",
      client_secret_write: "SECRET",
    });
    expect(await screen.findByText(/schwab credentials saved/i)).toBeInTheDocument();
  });

  it("shows an error toast when the authorize request fails", async () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    vi.mocked(fetchSchwabAuthorizeUrl).mockRejectedValueOnce(
      new Error("Schwab is not configured. Add your Schwab API credentials in Settings."),
    );
    renderWithProviders();
    await userEvent.click(screen.getByRole("button", { name: /connect schwab/i }));
    expect(await screen.findByText(/schwab is not configured/i)).toBeInTheDocument();
  });
});
