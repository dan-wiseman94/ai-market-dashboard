// frontend/src/__tests__/ConnectionsSettings.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ConnectionsSettings from "@/pages/settings/ConnectionsSettings";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { ToastProvider } from "@/hooks/useToast";
import { Toasts } from "@/components/Toasts";

const mockUseSchwabStatus = vi.fn();
vi.mock("@/hooks/useSchwabStatus", () => ({ useSchwabStatus: () => mockUseSchwabStatus() }));
vi.mock("@/api/schwab", () => ({ fetchSchwabAuthorizeUrl: vi.fn(async () => ({ url: "/x" })) }));
vi.mock("@/hooks/useCalendarOverrides", () => ({
  useCalendarOverrides: () => ({ data: [] }),
  useCreateCalendarOverride: () => ({ mutate: vi.fn() }),
  useDeleteCalendarOverride: () => ({ mutate: vi.fn() }),
}));

// useToast() throws without a provider; AppLayout supplies one in production. Mirror that.
function renderWithToasts() {
  return render(
    <ToastProvider>
      <ConnectionsSettings />
      <Toasts />
    </ToastProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("ConnectionsSettings", () => {
  it("shows not-connected state with a Connect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    renderWithToasts();
    expect(screen.getByText(/not connected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect schwab/i })).toBeInTheDocument();
  });

  it("shows connected state with a Reconnect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: true, expires_at: null }, isLoading: false });
    renderWithToasts();
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
  });

  it("shows an error toast when the authorize request fails", async () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    vi.mocked(fetchSchwabAuthorizeUrl).mockRejectedValueOnce(
      new Error("Schwab is not configured. Set SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET in .env."),
    );
    renderWithToasts();
    await userEvent.click(screen.getByRole("button", { name: /connect schwab/i }));
    expect(await screen.findByText(/schwab is not configured/i)).toBeInTheDocument();
  });
});
