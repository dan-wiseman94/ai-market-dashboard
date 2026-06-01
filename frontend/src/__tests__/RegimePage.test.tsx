import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import RegimePage from "@/pages/RegimePage";
import { renderWithProviders } from "./testUtils";

describe("RegimePage", () => {
  it("renders the composite, axes, and drivers", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) => {
      const reading = {
        id: 1, created_at: "2026-06-01T12:00:00Z", composite: "Risk-Off",
        axes: { volatility: "Elevated", trend: "Downtrend" },
        drivers: ["VIX 24 — Elevated"], narrative: "Risk-off backdrop.", changed_axes: [],
      };
      return path.endsWith("/current/") ? reading : [reading];
    });
    renderWithProviders(<RegimePage />);
    await waitFor(() => expect(screen.getAllByText("Risk-Off").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Elevated/).length).toBeGreaterThan(0);
    expect(screen.getByText(/VIX 24/)).toBeInTheDocument();
  });

  it("shows an empty state when there is no reading", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) =>
      path.endsWith("/current/") ? null : [],
    );
    renderWithProviders(<RegimePage />);
    await waitFor(() => expect(screen.getByText(/no regime reading/i)).toBeInTheDocument());
  });
});
