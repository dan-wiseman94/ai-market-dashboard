// frontend/src/__tests__/MarketStatusBadge.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MarketStatusBadge from "@/components/MarketStatusBadge";

const mockUse = vi.fn();
vi.mock("@/hooks/useMarketStatus", () => ({ useMarketStatus: () => mockUse() }));

beforeEach(() => mockUse.mockReset());

describe("MarketStatusBadge", () => {
  it("shows Open when the single market is open", () => {
    mockUse.mockReturnValue({ data: { markets: { us_equity: { is_open: true, phase: "open" } } } });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("Open");
  });

  it("shows Closed when the single market is closed", () => {
    mockUse.mockReturnValue({ data: { markets: { us_equity: { is_open: false, phase: "weekend" } } } });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("Closed");
  });

  it("summarizes N/M when multiple markets present", () => {
    mockUse.mockReturnValue({
      data: { markets: { us_equity: { is_open: false }, crypto: { is_open: true } } },
    });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("1/2 open");
  });

  it("renders nothing while loading (no data)", () => {
    mockUse.mockReturnValue({ data: undefined });
    const { container } = render(<MarketStatusBadge />);
    expect(container).toBeEmptyDOMElement();
  });
});
