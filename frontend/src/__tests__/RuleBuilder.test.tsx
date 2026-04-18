import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import RuleBuilder from "../components/triggers/RuleBuilder";
import type { Condition } from "../api/triggers";

describe("RuleBuilder", () => {
  it("renders the top-level group selector and one empty leaf row", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByText(/Fire when/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("SPY")).toBeInTheDocument();
    expect(screen.getByDisplayValue("550")).toBeInTheDocument();
  });

  it("emits updated condition when a leaf value changes", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const valueInput = screen.getByDisplayValue("550") as HTMLInputElement;
    fireEvent.change(valueInput, { target: { value: "560" } });
    expect(onChange).toHaveBeenCalled();
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect(emitted).toEqual({ all: [{ metric: "price", ticker: "SPY", op: ">", value: 560 }] });
  });

  it("adds a new leaf row on + Add condition", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add condition/i }));
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("all" in emitted && emitted.all.length).toBe(2);
  });

  it("removes a leaf when x button clicked", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [
      { metric: "price", ticker: "SPY", op: ">", value: 550 },
      { metric: "vix", op: ">", value: 20 },
    ]};
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const removeButtons = screen.getAllByRole("button", { name: /remove condition/i });
    fireEvent.click(removeButtons[1]);
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("all" in emitted && emitted.all.length).toBe(1);
  });

  it("shows natural-language echo under each leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByText(/price of SPY is greater than 550/i)).toBeInTheDocument();
  });

  it("toggles all/any at the top level", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const groupSelect = screen.getByLabelText(/group operator/i) as HTMLSelectElement;
    fireEvent.change(groupSelect, { target: { value: "any" } });
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    expect("any" in emitted).toBe(true);
  });
});
