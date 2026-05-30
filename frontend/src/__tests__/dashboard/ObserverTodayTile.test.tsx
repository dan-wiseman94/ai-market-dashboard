import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ObserverTodayTile } from "@/components/dashboard/ObserverTodayTile";
import { renderWithProviders } from "../testUtils";

describe("ObserverTodayTile", () => {
  it("shows runs_today and enabled_schedules counts", () => {
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 5, enabled_schedules: 3 }} />,
    );
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("5");
    expect(
      screen.getByTestId("observer-enabled-schedules").textContent,
    ).toBe("3");
  });

  it("shows '0 runs today' when there are none", () => {
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 0, enabled_schedules: 0 }} />,
    );
    expect(screen.getByTestId("observer-runs-today").textContent).toBe("0");
    expect(screen.getByText("runs today")).toBeInTheDocument();
  });

  it("links to /schedules", () => {
    renderWithProviders(
      <ObserverTodayTile observer={{ runs_today: 2, enabled_schedules: 4 }} />,
    );
    const link = screen.getByRole("link", { name: /schedules/i });
    expect(link).toHaveAttribute("href", "/schedules");
  });
});
