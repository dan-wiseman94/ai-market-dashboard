// frontend/src/__tests__/CapMeter.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CapMeter from "@/components/settings/CapMeter";

describe("CapMeter", () => {
  it("shows spent / cap and a rounded percentage", () => {
    render(<CapMeter label="Daily" cap="10.00" spent="6.00" pct={0.6} />);
    expect(screen.getByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("$6.00 / $10.00")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("caps the bar width at 100% when over budget", () => {
    render(<CapMeter label="Daily" cap="10.00" spent="25.00" pct={2.5} />);
    const fill = screen.getByTestId("capmeter-fill");
    expect(fill).toHaveStyle({ width: "100%" });
    expect(screen.getByText("250%")).toBeInTheDocument();
  });
});
