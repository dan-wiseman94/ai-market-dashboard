// frontend/src/__tests__/ConnectionsSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ConnectionsSettings from "@/pages/settings/ConnectionsSettings";

const mockUseSchwabStatus = vi.fn();
vi.mock("@/hooks/useSchwabStatus", () => ({ useSchwabStatus: () => mockUseSchwabStatus() }));
vi.mock("@/api/schwab", () => ({ fetchSchwabAuthorizeUrl: vi.fn(async () => ({ url: "/x" })) }));

beforeEach(() => vi.clearAllMocks());

describe("ConnectionsSettings", () => {
  it("shows not-connected state with a Connect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    render(<ConnectionsSettings />);
    expect(screen.getByText(/not connected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect schwab/i })).toBeInTheDocument();
  });

  it("shows connected state with a Reconnect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: true, expires_at: null }, isLoading: false });
    render(<ConnectionsSettings />);
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
  });
});
