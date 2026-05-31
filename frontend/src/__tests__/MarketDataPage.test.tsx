import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MarketDataPage from "@/pages/MarketDataPage";

const mockUseMacro = vi.fn();
const mockUseTreasury = vi.fn();
const mockUseFilings = vi.fn();
vi.mock("@/hooks/useMarketData", () => ({
  useMacro: () => mockUseMacro(),
  useTreasury: () => mockUseTreasury(),
  useFilings: (tickers: string[]) => mockUseFilings(tickers),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockUseMacro.mockReturnValue({
    data: { DGS10: { label: "10Y yield", value: 4.25, date: "2026-05-30", prev: 4.1, change: 0.15 } },
    isLoading: false,
  });
  mockUseTreasury.mockReturnValue({
    data: {
      rates: { record_date: "2026-05-30", rates: { "Treasury Notes": 3.5 } },
      debt: { record_date: "2026-05-30", total_public_debt: 34_000_000_000_000 },
    },
    isLoading: false,
  });
  mockUseFilings.mockReturnValue({ data: {}, isLoading: false });
});

describe("MarketDataPage", () => {
  it("renders macro indicators from FRED", () => {
    render(<MarketDataPage />);
    expect(screen.getByText("10Y yield")).toBeInTheDocument();
    expect(screen.getByText("4.25")).toBeInTheDocument();
  });

  it("renders treasury rates and total debt", () => {
    render(<MarketDataPage />);
    expect(screen.getByText("Treasury Notes")).toBeInTheDocument();
    expect(screen.getByText(/total public debt/i)).toBeInTheDocument();
  });

  it("shows a hint to add a FRED key when macro is empty", () => {
    mockUseMacro.mockReturnValue({ data: {}, isLoading: false });
    render(<MarketDataPage />);
    expect(screen.getByText(/add a FRED key/i)).toBeInTheDocument();
  });

  it("loads filings for entered tickers", async () => {
    mockUseFilings.mockImplementation((tickers: string[]) => ({
      data: tickers.length
        ? {
            AAPL: [
              { form: "10-K", filed: "2026-05-01", report_date: "", accession: "a1", title: "Apple 10-K", url: "u" },
            ],
          }
        : {},
      isLoading: false,
    }));
    render(<MarketDataPage />);
    await userEvent.type(screen.getByLabelText("Tickers"), "AAPL");
    await userEvent.click(screen.getByRole("button", { name: /load filings/i }));
    expect(await screen.findByText("Apple 10-K")).toBeInTheDocument();
  });
});
