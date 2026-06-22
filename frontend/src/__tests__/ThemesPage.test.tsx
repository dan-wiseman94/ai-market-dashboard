import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as hooks from "@/hooks/useThemes";
import ThemesPage from "@/pages/ThemesPage";

function setup(themes: unknown, health: unknown) {
  vi.spyOn(hooks, "useThemes").mockReturnValue({ data: themes, isLoading: false } as never);
  vi.spyOn(hooks, "useThemeHealth").mockReturnValue({ data: health } as never);
  vi.spyOn(hooks, "useCreateTheme").mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  vi.spyOn(hooks, "useDeleteTheme").mockReturnValue({ mutate: vi.fn() } as never);
}

describe("ThemesPage", () => {
  it("lists themes and renders narrative health", () => {
    setup(
      [{ id: 1, name: "AI-capex", tickers: ["NVDA", "AMD"], note: "", created_at: "", updated_at: "" }],
      {
        window_days: 20,
        coverage: { priced: 2, total: 2 },
        breadth: 0.5,
        mean_return_pct: 2.5,
        spx_return_pct: 2.0,
        relative_strength: 0.5,
        leadership: { leader: { ticker: "NVDA", return_pct: 10 }, laggard: { ticker: "AMD", return_pct: -5 } },
        members: [
          { ticker: "NVDA", return_pct: 10, above_theme: true },
          { ticker: "AMD", return_pct: -5, above_theme: false },
        ],
      },
    );
    render(<ThemesPage />);
    expect(screen.getByText("AI-capex")).toBeInTheDocument();
    fireEvent.click(screen.getByText("AI-capex")); // select the theme to load its health
    const health = screen.getByTestId("theme-health");
    expect(health).toHaveTextContent(/Breadth/);
    expect(health).toHaveTextContent(/relative strength/i);
    expect(health).toHaveTextContent(/Leader NVDA/);
  });

  it("shows empty state with no themes", () => {
    setup([], undefined);
    render(<ThemesPage />);
    expect(screen.getByText(/No themes yet/i)).toBeInTheDocument();
  });
});
