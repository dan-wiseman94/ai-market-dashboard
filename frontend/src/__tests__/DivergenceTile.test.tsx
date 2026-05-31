import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DivergenceTile } from "@/components/dashboard/DivergenceTile";
import * as hooks from "@/hooks/usePredictions";

function mockDiv(data: unknown) {
  vi.spyOn(hooks, "useDivergences").mockReturnValue({ data } as never);
}

function renderTile() {
  return render(
    <MemoryRouter>
      <DivergenceTile />
    </MemoryRouter>,
  );
}

describe("DivergenceTile", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the empty state when nothing diverges", () => {
    mockDiv({ count: 0, rows: [] });
    renderTile();
    expect(screen.getByText(/No divergences/i)).toBeInTheDocument();
  });

  it("lists diverging theses with a link to the thesis", () => {
    mockDiv({
      count: 1,
      rows: [
        {
          thesis_id: 7,
          ticker: "NVDA",
          title: "x",
          thesis_direction: "bullish",
          conviction: 4,
          ai_direction: "bearish",
          ai_confidence: 0.6,
          ai_horizon_days: 7,
          agreement: "diverge",
        },
      ],
    });
    renderTile();
    expect(screen.getByTestId("divergence-tile")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toHaveAttribute("href", "/theses/7");
    expect(screen.getByText(/you bullish · AI bearish/)).toBeInTheDocument();
    expect(screen.getByText("diverge")).toBeInTheDocument();
  });
});
