import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ToolCallTrace } from "../components/ToolCallTrace";

describe("ToolCallTrace", () => {
  it("renders nothing when empty", () => {
    const { container } = render(<ToolCallTrace calls={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders tool name + compact input summary + latency", () => {
    render(
      <ToolCallTrace
        calls={[{
          toolUseId: "tu1", name: "get_quote", input: { ticker: "AAPL" },
          ok: true, latencyMs: 42,
        }]}
      />,
    );
    expect(screen.getByText("get_quote")).toBeInTheDocument();
    expect(screen.getByText(/AAPL/)).toBeInTheDocument();
    expect(screen.getByText(/42\s*ms/)).toBeInTheDocument();
  });

  it("expands to show full JSON on click", () => {
    const { container } = render(
      <ToolCallTrace
        calls={[{
          toolUseId: "tu1", name: "fetch_ohlc",
          input: { ticker: "SPY", timeframe: "1d", bars: 30 },
          ok: true, latencyMs: 10, result: [{ close: 1 }],
        }]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /fetch_ohlc/i }));
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain("timeframe");
    expect(pre?.textContent).toContain("close");
  });

  it("renders an error indicator for failed calls", () => {
    render(
      <ToolCallTrace
        calls={[{
          toolUseId: "tu1", name: "get_quote", input: {},
          ok: false, error: "rate limited", latencyMs: 5,
        }]}
      />,
    );
    expect(screen.getByText(/rate limited/)).toBeInTheDocument();
  });
});
