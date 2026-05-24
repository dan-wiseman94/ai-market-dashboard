import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import Settings from "@/pages/Settings";

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: vi.fn(() => ({ data: [], isLoading: false })),
  useUpsertProviderConfig: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock("@/hooks/useAiUsage", () => ({
  useAiUsage: vi.fn(() => ({ data: null })),
}));

vi.mock("@/hooks/useSchwabStatus", () => ({
  useSchwabStatus: vi.fn(() => ({ data: { connected: false }, isLoading: false })),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Settings", () => {
  it("renders the Settings page heading", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByRole("heading", { level: 1, name: /settings/i })).toBeInTheDocument();
  });

  it("renders the SchwabConnectionCard section", () => {
    renderWithProviders(<Settings />);
    // SchwabConnectionCard shows connect prompt when not connected
    expect(screen.getByRole("heading", { name: /charles schwab/i })).toBeInTheDocument();
  });

  it("renders the ProviderConfigCard section with AI providers heading", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByRole("heading", { name: /ai providers/i })).toBeInTheDocument();
  });
});
