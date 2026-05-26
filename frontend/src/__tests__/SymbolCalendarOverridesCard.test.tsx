// frontend/src/__tests__/SymbolCalendarOverridesCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SymbolCalendarOverridesCard from "@/components/SymbolCalendarOverridesCard";
import type { CalendarOverride } from "@/api/market";

const mockCreate = vi.fn();
const mockDelete = vi.fn();
const mockUseOverrides = vi.fn();

vi.mock("@/hooks/useCalendarOverrides", () => ({
  useCalendarOverrides: () => mockUseOverrides(),
  useCreateCalendarOverride: () => ({ mutate: mockCreate }),
  useDeleteCalendarOverride: () => ({ mutate: mockDelete }),
}));

const rows: CalendarOverride[] = [
  { id: 1, symbol: "BTC-USD", market_key: "crypto", note: "", created_at: "", updated_at: "" },
];

beforeEach(() => {
  mockUseOverrides.mockReturnValue({ data: rows });
  mockCreate.mockReset();
  mockDelete.mockReset();
});

describe("SymbolCalendarOverridesCard", () => {
  it("lists existing overrides", () => {
    render(<SymbolCalendarOverridesCard />);
    expect(screen.getByText("BTC-USD")).toBeInTheDocument();
    expect(screen.getByText(/crypto/i)).toBeInTheDocument();
  });

  it("submitting the add form calls create with the symbol + market", async () => {
    const user = userEvent.setup();
    render(<SymbolCalendarOverridesCard />);
    await user.type(screen.getByPlaceholderText(/symbol/i), "eth-usd");
    await user.selectOptions(screen.getByLabelText(/market/i), "crypto");
    await user.click(screen.getByRole("button", { name: /add/i }));
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ symbol: "eth-usd", market_key: "crypto" });
  });

  it("clicking delete calls delete with the id", async () => {
    const user = userEvent.setup();
    render(<SymbolCalendarOverridesCard />);
    await user.click(screen.getByRole("button", { name: /delete BTC-USD/i }));
    expect(mockDelete).toHaveBeenCalledWith(1);
  });
});
