import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RegimeTile } from "@/components/RegimeTile";
import { renderWithProviders } from "./testUtils";

describe("RegimeTile", () => {
  it("renders the composite + first driver", () => {
    renderWithProviders(
      <RegimeTile regime={{ composite: "Risk-Off", drivers: ["VIX 24 — Elevated"], as_of: "2026-06-01T12:00:00Z" }} />,
    );
    expect(screen.getByText("Risk-Off")).toBeInTheDocument();
    expect(screen.getByText(/VIX 24/)).toBeInTheDocument();
  });

  it("renders gracefully with the empty default", () => {
    renderWithProviders(<RegimeTile regime={{ composite: null, drivers: [], as_of: null }} />);
    expect(screen.getByText(/no reading/i)).toBeInTheDocument();
  });
});
