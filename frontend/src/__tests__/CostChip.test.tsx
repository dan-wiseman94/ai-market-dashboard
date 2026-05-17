import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import CostChip from "@/components/CostChip";

vi.mock("@/hooks/useCosts", () => ({
  useCostsToday: vi.fn(),
}));

import { useCostsToday } from "@/hooks/useCosts";

const mockUseCostsToday = useCostsToday as ReturnType<typeof vi.fn>;

describe("CostChip", () => {
  it("renders cost when useCostsToday returns data", () => {
    mockUseCostsToday.mockReturnValue({ data: { total_usd: 0.1234 } });
    render(
      <MemoryRouter>
        <CostChip />
      </MemoryRouter>,
    );
    expect(screen.getByText("$0.1234")).toBeInTheDocument();
  });

  it("renders $0.0000 when data is null", () => {
    mockUseCostsToday.mockReturnValue({ data: null });
    render(
      <MemoryRouter>
        <CostChip />
      </MemoryRouter>,
    );
    expect(screen.getByText("$0.0000")).toBeInTheDocument();
  });

  it("has a Link pointing to /costs", () => {
    mockUseCostsToday.mockReturnValue({ data: null });
    render(
      <MemoryRouter>
        <CostChip />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/costs");
  });
});
