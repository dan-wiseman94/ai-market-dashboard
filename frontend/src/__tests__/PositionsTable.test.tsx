import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { usePositions } from "@/hooks/usePositions";
import PositionsTable from "@/components/PositionsTable";
import { plClass } from "@/utils/format";

vi.mock("@/hooks/usePositions", () => ({
  usePositions: vi.fn(),
}));

const mockUsePositions = vi.mocked(usePositions);

const makePosition = (overrides = {}) => ({
  ticker: "AAPL",
  qty: 10,
  avg_cost: 150.0,
  mkt_value: 1600.0,
  unrealized_pl: 100.0,
  day_pl: 5.0,
  ...overrides,
});

describe("PositionsTable", () => {
  beforeEach(() => {
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: false, error: null } as unknown as ReturnType<typeof usePositions>);
  });

  it("renders loading state", () => {
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: true, error: null } as unknown as ReturnType<typeof usePositions>);
    render(<PositionsTable />);
    expect(screen.getByText("Loading the book…")).toBeInTheDocument();
  });

  it("renders error message from error.message", () => {
    const err = new Error("network failure");
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: false, error: err } as unknown as ReturnType<typeof usePositions>);
    render(<PositionsTable />);
    expect(screen.getByText(/network failure/)).toBeInTheDocument();
    expect(screen.getByText(/Could not load positions/)).toBeInTheDocument();
  });

  it("renders empty state when data is an empty array", () => {
    mockUsePositions.mockReturnValue({ data: [], isLoading: false, error: null } as unknown as ReturnType<typeof usePositions>);
    render(<PositionsTable />);
    expect(screen.getByText("Flat.")).toBeInTheDocument();
    expect(screen.getByText("No open positions.")).toBeInTheDocument();
  });

  it("renders one row per position with Book totals footer", () => {
    const positions = [
      makePosition({ ticker: "AAPL", day_pl: 5.0, unrealized_pl: 100.0 }),
      makePosition({ ticker: "TSLA", qty: 5, avg_cost: 200.0, mkt_value: 1000.0, day_pl: -10.0, unrealized_pl: 50.0 }),
    ];
    mockUsePositions.mockReturnValue({ data: positions, isLoading: false, error: null } as unknown as ReturnType<typeof usePositions>);
    render(<PositionsTable />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByText("Book totals")).toBeInTheDocument();
    // Day total: 5 + (-10) = -5; unrealized total: 100 + 50 = 150
    expect(screen.getByText("-5.00")).toBeInTheDocument();
    expect(screen.getByText("+150.00")).toBeInTheDocument();
  });

  it("positive day_pl and negative day_pl get different plClass colors", () => {
    const positions = [
      makePosition({ ticker: "GAIN", day_pl: 10.0, unrealized_pl: 0 }),
      makePosition({ ticker: "LOSS", day_pl: -10.0, unrealized_pl: 0 }),
    ];
    mockUsePositions.mockReturnValue({ data: positions, isLoading: false, error: null } as unknown as ReturnType<typeof usePositions>);
    const { container } = render(<PositionsTable />);
    const gainClass = plClass(10.0);
    const lossClass = plClass(-10.0);
    expect(gainClass).not.toBe(lossClass);
    expect(container.querySelector(`.${gainClass.replace(/\//g, "\\/")}`)).not.toBeNull();
    expect(container.querySelector(`.${lossClass.replace(/\//g, "\\/")}`)).not.toBeNull();
  });
});
