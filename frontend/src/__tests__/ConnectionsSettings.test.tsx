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
// ConnectionsSettings now embeds the DataSourcesPanel; stub its hook so it doesn't fetch.
vi.mock("@/hooks/useDataSources", () => ({
  useDataSources: () => ({ data: { data_sources: [] }, isLoading: false }),
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

  it("warns when a stored credential was rejected by Schwab (auth_error)", () => {
    // A row exists (connected=true) but Schwab rejected the token — reads have
    // silently fallen back to a free provider. The user must be told.
    mockUseSchwabStatus.mockReturnValue({
      data: {
        connected: true,
        expires_at: null,
        auth_error: "Schwab rejected the stored authorization. Reconnect at /settings.",
      },
      isLoading: false,
    });
    renderWithProviders();
    expect(screen.getByText(/rejected the stored authorization/i)).toBeInTheDocument();
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

  it("opens the Schwab authorize URL in a new tab, not the current one", async () => {
    // A full-page redirect (window.location.href) hands the whole dashboard tab to
    // Schwab's hosted page; if Schwab rejects the app key with 401 invalid_client the
    // user is stranded on that error page. Opening a new tab keeps the dashboard intact.
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    vi.mocked(fetchSchwabAuthorizeUrl).mockResolvedValueOnce({
      url: "https://api.schwabapi.com/v1/oauth/authorize?client_id=x",
    });
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    renderWithProviders();
    await userEvent.click(screen.getByRole("button", { name: /connect schwab/i }));
    expect(openSpy).toHaveBeenCalledWith(
      "https://api.schwabapi.com/v1/oauth/authorize?client_id=x",
      "_blank",
      "noopener,noreferrer",
    );
    openSpy.mockRestore();
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
