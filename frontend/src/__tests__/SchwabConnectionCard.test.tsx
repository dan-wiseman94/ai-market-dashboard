import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import SchwabConnectionCard from "@/components/SchwabConnectionCard";

vi.mock("@/hooks/useSchwabStatus", () => ({
  useSchwabStatus: vi.fn(),
}));

vi.mock("@/api/schwab", () => ({
  fetchSchwabAuthorizeUrl: vi.fn(),
}));

// NOTE: We verify that fetchSchwabAuthorizeUrl is called when the button is clicked.
// Asserting window.location.href navigation is brittle in jsdom and is intentionally
// omitted — the function call itself is the observable side-effect under test.

const mockUseSchwabStatus = vi.mocked(useSchwabStatus);
const mockFetchSchwabAuthorizeUrl = vi.mocked(fetchSchwabAuthorizeUrl);

beforeEach(() => {
  mockUseSchwabStatus.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<typeof useSchwabStatus>);
  mockFetchSchwabAuthorizeUrl.mockResolvedValue({ url: "https://schwab.com/auth" });
});

describe("SchwabConnectionCard", () => {
  it("shows 'Checking Schwab…' when loading", () => {
    mockUseSchwabStatus.mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useSchwabStatus>);
    render(<SchwabConnectionCard />);
    expect(screen.getByText("Checking Schwab…")).toBeInTheDocument();
  });

  it("shows 'Connected' and 'Reconnect' button when connected", () => {
    mockUseSchwabStatus.mockReturnValue({
      data: { connected: true, expires_at: null },
      isLoading: false,
    } as ReturnType<typeof useSchwabStatus>);
    render(<SchwabConnectionCard />);
    expect(screen.getByText(/Connected/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reconnect/i })).toBeInTheDocument();
  });

  it("shows 'Not connected' and 'Connect Schwab' button when disconnected", () => {
    mockUseSchwabStatus.mockReturnValue({
      data: { connected: false, expires_at: null },
      isLoading: false,
    } as ReturnType<typeof useSchwabStatus>);
    render(<SchwabConnectionCard />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Connect Schwab/i })).toBeInTheDocument();
  });

  it("shows formatted distance when connected with expires_at", () => {
    // Set expires_at to 30 minutes in the future
    const future = new Date(Date.now() + 30 * 60 * 1000).toISOString();
    mockUseSchwabStatus.mockReturnValue({
      data: { connected: true, expires_at: future },
      isLoading: false,
    } as ReturnType<typeof useSchwabStatus>);
    render(<SchwabConnectionCard />);
    // formatDistanceToNow returns something like "in 30 minutes"
    const text = screen.getByText(/Connected/).textContent ?? "";
    expect(text).toContain("in ");
  });

  it("clicking the connect button calls fetchSchwabAuthorizeUrl once", async () => {
    const user = userEvent.setup();
    mockUseSchwabStatus.mockReturnValue({
      data: { connected: false, expires_at: null },
      isLoading: false,
    } as ReturnType<typeof useSchwabStatus>);
    render(<SchwabConnectionCard />);
    await user.click(screen.getByRole("button", { name: /Connect Schwab/i }));
    expect(mockFetchSchwabAuthorizeUrl).toHaveBeenCalledTimes(1);
  });
});
