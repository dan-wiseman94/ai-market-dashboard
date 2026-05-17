import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import Dashboard from "@/pages/Dashboard";

// Mock all child components' hooks to keep test surface flat
vi.mock("@/hooks/useMarketContext", () => ({
  useMarketContext: vi.fn(() => ({ data: null, isLoading: false })),
}));

vi.mock("@/hooks/usePositions", () => ({
  usePositions: vi.fn(() => ({ data: [], isLoading: false, error: null })),
}));

vi.mock("@/hooks/useCosts", () => ({
  useCostsToday: vi.fn(() => ({ data: null })),
}));

// RecentTriggersCard uses useQuery directly against fetchRecentFirings
vi.mock("@/api/triggers", () => ({
  fetchRecentFirings: vi.fn(() => Promise.resolve([])),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Dashboard", () => {
  it("renders without crashing", () => {
    renderWithProviders(<Dashboard />);
    // header section exists
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("includes a time-based greeting in the hero heading", () => {
    renderWithProviders(<Dashboard />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/good morning|good afternoon|good evening|late watch/i);
  });

  it("includes the 'Market context' section label", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/market context/i)).toBeInTheDocument();
  });

  it("includes the 'The book' section label (positions area)", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText(/the book/i)).toBeInTheDocument();
  });

  it("includes a 'Capture snapshot' call-to-action link", () => {
    renderWithProviders(<Dashboard />);
    const ctaLink = screen.getByRole("link", { name: /capture snapshot/i });
    expect(ctaLink).toBeInTheDocument();
    expect(ctaLink).toHaveAttribute("href", "/snapshot");
  });

  it("includes a 'Watchlists' navigation link in the book section", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByRole("link", { name: /watchlists/i })).toBeInTheDocument();
  });
});
