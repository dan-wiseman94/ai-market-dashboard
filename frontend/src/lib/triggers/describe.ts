import type { Condition, Leaf, Op } from "@/api/triggers";

const OP_WORDS: Record<Op, string> = {
  ">": "is greater than",
  ">=": "is greater than or equal to",
  "<": "is less than",
  "<=": "is less than or equal to",
  "==": "equals",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};

function pctPrecision(value: number): number {
  return Math.abs(value) < 0.01 ? 2 : 0;
}

// Fraction -> percentage magnitude string, e.g. -0.05 -> "5", 0.001 -> "0.10".
function pctMagnitude(value: number): string {
  return Math.abs(value * 100).toFixed(pctPrecision(value));
}

function pctLabel(value: number, dir: Op): string {
  const sign = dir === "==" ? "=" : "≥";
  return `${sign}${pctMagnitude(value)}%`;
}

export function describeLeaf(leaf: Leaf): string {
  const { metric, op, value, ticker, window } = leaf;

  if (metric === "pct_change") {
    return `${ticker} moved ${pctLabel(value, op)} over ${window}`;
  }

  if (metric === "volume_z") {
    return `${ticker} volume z-score ${OP_WORDS[op]} ${value} over ${window}`;
  }

  if (metric === "position_pl_pct") {
    const verb = value < 0 ? "down" : "up";
    return `portfolio is ${verb} ≥${pctMagnitude(value)}%`;
  }

  if (metric === "position_pl") {
    return `portfolio unrealized P/L ${OP_WORDS[op]} ${value}`;
  }

  if (metric === "vix") {
    return `VIX ${OP_WORDS[op]} ${value}`;
  }

  // price
  return `${metric} of ${ticker} ${OP_WORDS[op]} ${value}`;
}

export function describeCondition(node: Condition): string {
  if ("all" in node) {
    return node.all.map(describeCondition).join(" AND ");
  }
  if ("any" in node) {
    return node.any.map(describeCondition).join(" OR ");
  }
  if ("not" in node) {
    return `NOT (${describeCondition(node.not)})`;
  }
  return describeLeaf(node);
}
