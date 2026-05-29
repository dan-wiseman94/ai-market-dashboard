import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import RuleBuilder from "../components/triggers/RuleBuilder";
import type { Condition, Leaf } from "../api/triggers";

describe("TriggerEditorParams", () => {
  it("selecting rsi in the metric dropdown reveals a period input", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);

    const metricSelect = screen.getByLabelText("metric") as HTMLSelectElement;
    fireEvent.change(metricSelect, { target: { value: "rsi" } });

    // After onChange is called, re-render with the new leaf
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaf = ("all" in emitted ? emitted.all[0] : emitted) as Leaf;
    expect(leaf.metric).toBe("rsi");

    // Now render with the updated RSI leaf to see the period input
    const { unmount } = render(
      <RuleBuilder
        value={{ all: [{ metric: "rsi", ticker: "SPY", op: ">", value: 30, window: "1d" }] }}
        onChange={onChange}
      />
    );
    expect(screen.getByLabelText("period")).toBeInTheDocument();
    unmount();
  });

  it("period input shows for rsi leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "rsi", ticker: "SPY", op: "<", value: 30, window: "1d" }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByLabelText("period")).toBeInTheDocument();
  });

  it("fast and slow inputs show for sma_spread_pct leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "sma_spread_pct", ticker: "SPY", op: ">", value: 0, window: "1d", params: { fast: 50, slow: 200 } }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByLabelText("fast period")).toBeInTheDocument();
    expect(screen.getByLabelText("slow period")).toBeInTheDocument();
  });

  it("no params sub-form for price leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "price", ticker: "SPY", op: ">", value: 550 }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.queryByLabelText("period")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("fast period")).not.toBeInTheDocument();
  });

  it("SMA cross preset button is present", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByRole("button", { name: /SMA cross/i })).toBeInTheDocument();
  });

  it("clicking SMA cross preset emits a sma_spread_pct leaf with fast/slow params and crosses_above op", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /SMA cross/i }));

    expect(onChange).toHaveBeenCalled();
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaves = ("all" in emitted ? emitted.all : []) as Leaf[];
    // The new leaf should be the second one (appended)
    const newLeaf = leaves[leaves.length - 1];
    expect(newLeaf.metric).toBe("sma_spread_pct");
    expect(newLeaf.op).toBe("crosses_above");
    expect(newLeaf.value).toBe(0);
    expect(newLeaf.params?.fast).toBeDefined();
    expect(newLeaf.params?.slow).toBeDefined();
  });

  it("period input change updates the leaf params", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "rsi", ticker: "SPY", op: "<", value: 30, window: "1d", params: { period: 14 } }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);

    const periodInput = screen.getByLabelText("period") as HTMLInputElement;
    fireEvent.change(periodInput, { target: { value: "21" } });

    expect(onChange).toHaveBeenCalled();
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaf = ("all" in emitted ? emitted.all[0] : emitted) as Leaf;
    expect(leaf.params?.period).toBe(21);
  });
});
