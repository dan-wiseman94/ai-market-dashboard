import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ArmedTriggersTile } from "@/components/dashboard/ArmedTriggersTile";
import { renderWithProviders } from "../testUtils";
import type { DashboardTriggers } from "@/hooks/useDashboard";

const triggersWithFirings: DashboardTriggers = {
  armed_count: 7,
  latest_firings: [
    {
      id: 42,
      trigger_id: 10,
      trigger_name: "AAPL breakout",
      fired_at: "2026-05-30T09:45:00Z",
      cost_capped: false,
    },
    {
      id: 43,
      trigger_id: 11,
      trigger_name: "VIX spike",
      fired_at: "2026-05-30T10:00:00Z",
      cost_capped: true,
    },
  ],
};

describe("ArmedTriggersTile", () => {
  it("shows armed_count", () => {
    renderWithProviders(<ArmedTriggersTile triggers={triggersWithFirings} />);
    expect(screen.getByTestId("triggers-armed-count").textContent).toBe("7");
  });

  it("shows latest firing names", () => {
    renderWithProviders(<ArmedTriggersTile triggers={triggersWithFirings} />);
    expect(screen.getByText("AAPL breakout")).toBeInTheDocument();
    expect(screen.getByText("VIX spike")).toBeInTheDocument();
  });

  it("shows 'capped' pill on cost_capped firings", () => {
    renderWithProviders(<ArmedTriggersTile triggers={triggersWithFirings} />);
    expect(screen.getByText("capped")).toBeInTheDocument();
  });

  it("shows EmptyState when no firings", () => {
    renderWithProviders(
      <ArmedTriggersTile triggers={{ armed_count: 2, latest_firings: [] }} />,
    );
    expect(screen.getByText(/No recent firings/i)).toBeInTheDocument();
    // armed count still shown
    expect(screen.getByTestId("triggers-armed-count").textContent).toBe("2");
  });

  it("links to /triggers", () => {
    renderWithProviders(<ArmedTriggersTile triggers={triggersWithFirings} />);
    const link = screen.getByRole("link", { name: /All/i });
    expect(link).toHaveAttribute("href", "/triggers");
  });
});
