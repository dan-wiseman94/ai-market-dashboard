import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useMarketContext } from "@/hooks/useMarketContext";
import MarketContextStrip from "@/components/MarketContextStrip";

vi.mock("@/hooks/useMarketContext", () => ({
  useMarketContext: vi.fn(),
}));

const mockUseMarketContext = vi.mocked(useMarketContext);

const baseData = {
  spy_last: 520.15,
  qqq_last: 445.32,
  vix_last: 14.75,
  sectors: {},
  breadth: {},
};

describe("MarketContextStrip", () => {
  beforeEach(() => {
    mockUseMarketContext.mockReturnValue({ data: undefined } as ReturnType<typeof useMarketContext>);
  });

  it("shows 'Awaiting tape…' when data is undefined", () => {
    render(<MarketContextStrip />);
    expect(screen.getByText("Awaiting tape…")).toBeInTheDocument();
  });

  it("renders SPY, QQQ, VIX values with 2 decimals when data is present", () => {
    mockUseMarketContext.mockReturnValue({ data: baseData } as ReturnType<typeof useMarketContext>);
    render(<MarketContextStrip />);
    expect(screen.getByText("520.15")).toBeInTheDocument();
    expect(screen.getByText("445.32")).toBeInTheDocument();
    expect(screen.getByText("14.75")).toBeInTheDocument();
  });

  it("VIX value carries the warn tone class text-copper-300", () => {
    mockUseMarketContext.mockReturnValue({ data: baseData } as ReturnType<typeof useMarketContext>);
    const { container } = render(<MarketContextStrip />);
    const vixValue = container.querySelector(".text-copper-300");
    expect(vixValue).not.toBeNull();
    expect(vixValue!.textContent).toBe("14.75");
  });

  it("renders one sector tile per entry when sectors is populated", () => {
    const data = {
      ...baseData,
      sectors: { XLK: 1.23, XLF: -0.45, XLE: 0.78 },
    };
    mockUseMarketContext.mockReturnValue({ data } as ReturnType<typeof useMarketContext>);
    render(<MarketContextStrip />);
    expect(screen.getByText("XLK")).toBeInTheDocument();
    expect(screen.getByText("XLF")).toBeInTheDocument();
    expect(screen.getByText("XLE")).toBeInTheDocument();
    expect(screen.getByText("3 tracked")).toBeInTheDocument();
  });

  it("does not render the Sectors section when sectors is empty", () => {
    mockUseMarketContext.mockReturnValue({ data: baseData } as ReturnType<typeof useMarketContext>);
    render(<MarketContextStrip />);
    expect(screen.queryByText("Sectors")).not.toBeInTheDocument();
    // All 3 headlines are still shown
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("QQQ")).toBeInTheDocument();
    expect(screen.getByText("VIX")).toBeInTheDocument();
  });

  it("renders em-dash for null numeric values", () => {
    const data = {
      spy_last: null,
      qqq_last: null,
      vix_last: null,
      sectors: {},
      breadth: {},
    };
    mockUseMarketContext.mockReturnValue({ data } as ReturnType<typeof useMarketContext>);
    render(<MarketContextStrip />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });
});
