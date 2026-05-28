import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import StreamingMessage from "@/components/StreamingMessage";

const SNAP = [
  "**Objective:** Name the biases at play.",
  "## Quotes",
  "| Ticker | Last |",
  "|---|---:|",
  "| SPY | 754 |",
  "## OHLC (SPY @ 1m)",
  "ts,open",
  "2026-01-01,1",
].join("\n\n");

describe("StreamingMessage — snapshot turn", () => {
  it("keeps the objective visible and collapses the data sections by default", () => {
    render(<StreamingMessage role="user" text={SNAP} status="done" snapshotId={42} />);
    expect(screen.getByText(/Name the biases at play/)).toBeInTheDocument();
    // The data tables are not in the DOM until expanded.
    expect(screen.queryByText(/## Quotes/)).not.toBeInTheDocument();
    // Toggle advertises the section names it will reveal.
    expect(screen.getByRole("button", { name: /snapshot data/i })).toBeInTheDocument();
    expect(screen.getByText(/Quotes, OHLC/)).toBeInTheDocument();
  });

  it("reveals the data on click", async () => {
    const user = userEvent.setup();
    render(<StreamingMessage role="user" text={SNAP} status="done" snapshotId={42} />);
    await user.click(screen.getByRole("button", { name: /snapshot data/i }));
    expect(screen.getByText(/## Quotes/)).toBeInTheDocument();
  });

  it("renders a plain typed prompt with no collapsible box", () => {
    render(<StreamingMessage role="user" text="just a question" status="done" />);
    expect(screen.getByText("just a question")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /snapshot data/i })).not.toBeInTheDocument();
  });
});
