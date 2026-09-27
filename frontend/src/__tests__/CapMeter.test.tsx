import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CapMeter from "@/components/settings/CapMeter";

describe("CapMeter", () => {

  it("caps the bar width at 100% when over budget", () => {
    render(<CapMeter label="Daily" cap="10.00" spent="25.00" pct={2.5} />);
    const fill = screen.getByTestId("capmeter-fill");
    expect(fill).toHaveStyle({ width: "100%" });
    expect(screen.getByText("250%")).toBeInTheDocument();
  });
});
