import { describe, expect, it } from "vitest";
import type { Condition, Leaf } from "../api/triggers";
import { describeCondition, describeLeaf } from "../lib/triggers/describe";

describe("describeLeaf", () => {
  it("formats price > 550 as 'price of SPY is greater than 550'", () => {
    const leaf: Leaf = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    expect(describeLeaf(leaf)).toBe("price of SPY is greater than 550");
  });

  it("formats pct_change with window", () => {
    const leaf: Leaf = { metric: "pct_change", ticker: "NVDA", op: ">=", value: 0.01, window: "5m" };
    expect(describeLeaf(leaf)).toBe("NVDA moved ≥1% over 5m");
  });

  it("formats vix with implied ticker", () => {
    expect(describeLeaf({ metric: "vix", op: ">", value: 30 }))
      .toBe("VIX is greater than 30");
  });

  it("formats position_pl", () => {
    expect(describeLeaf({ metric: "position_pl", op: "<", value: -500 }))
      .toBe("portfolio unrealized P/L is less than -500");
  });

  it("formats position_pl_pct", () => {
    expect(describeLeaf({ metric: "position_pl_pct", op: "<=", value: -0.05 }))
      .toBe("portfolio is down ≥5%");
  });

  it("formats crosses_above", () => {
    expect(describeLeaf({ metric: "price", ticker: "SPY", op: "crosses_above", value: 550 }))
      .toBe("price of SPY crosses above 550");
  });

  it("formats crosses_below", () => {
    expect(describeLeaf({ metric: "price", ticker: "SPY", op: "crosses_below", value: 550 }))
      .toBe("price of SPY crosses below 550");
  });
});

describe("describeCondition", () => {
  it("single leaf passes through", () => {
    const c: Condition = { metric: "price", ticker: "SPY", op: ">", value: 550 };
    expect(describeCondition(c)).toBe("price of SPY is greater than 550");
  });

  it("all group joined with AND", () => {
    const c: Condition = {
      all: [
        { metric: "price", ticker: "SPY", op: ">", value: 550 },
        { metric: "vix", op: ">", value: 20 },
      ],
    };
    expect(describeCondition(c)).toBe(
      "price of SPY is greater than 550 AND VIX is greater than 20",
    );
  });

  it("any group joined with OR", () => {
    const c: Condition = {
      any: [
        { metric: "price", ticker: "SPY", op: ">", value: 550 },
        { metric: "price", ticker: "QQQ", op: ">", value: 480 },
      ],
    };
    expect(describeCondition(c)).toBe(
      "price of SPY is greater than 550 OR price of QQQ is greater than 480",
    );
  });

  it("not wraps leaf with NOT", () => {
    const c: Condition = { not: { metric: "vix", op: ">", value: 30 } };
    expect(describeCondition(c)).toBe("NOT (VIX is greater than 30)");
  });
});
