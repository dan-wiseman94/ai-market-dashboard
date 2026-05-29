import type { Condition, Leaf } from "@/api/triggers";
import LeafRow from "./LeafRow";

export type GroupOp = "all" | "any";

export interface RuleBuilderProps {
  value: Condition;
  onChange: (next: Condition) => void;
  readOnly?: boolean;
}

function isGroup(c: Condition): c is { all: Condition[] } | { any: Condition[] } {
  return "all" in c || "any" in c;
}

function getGroupOp(c: Condition): GroupOp {
  return "any" in c ? "any" : "all";
}

function getLeaves(c: Condition): Leaf[] {
  if ("all" in c) return c.all as Leaf[];
  if ("any" in c) return c.any as Leaf[];
  // Single leaf at top level — wrap in all for the builder's shape.
  return [c as Leaf];
}

const EMPTY_LEAF: Leaf = { metric: "price", ticker: "SPY", op: ">", value: 0 };

const SMA_CROSS_PRESET: Leaf = {
  metric: "sma_spread_pct",
  ticker: "SPY",
  op: "crosses_above",
  value: 0,
  window: "1d",
  params: { fast: 50, slow: 200 },
};

export default function RuleBuilder({ value, onChange, readOnly }: RuleBuilderProps) {
  const op = isGroup(value) ? getGroupOp(value) : "all";
  const leaves = getLeaves(value);

  function emit(nextLeaves: Leaf[], nextOp: GroupOp = op) {
    onChange({ [nextOp]: nextLeaves } as Condition);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-neutral-400 flex-wrap">
        <span>Fire when</span>
        <select
          aria-label="group operator"
          value={op}
          onChange={(e) => emit(leaves, e.target.value as GroupOp)}
          className="bg-neutral-800 px-2 py-1 rounded"
          disabled={readOnly}
        >
          <option value="all">all</option>
          <option value="any">any</option>
        </select>
        <span>of:</span>
        {!readOnly && (
          <button
            type="button"
            aria-label="SMA cross preset"
            onClick={() => emit([...leaves, { ...SMA_CROSS_PRESET }])}
            className="ml-auto text-xs bg-neutral-800 hover:bg-neutral-700 px-2 py-1 rounded text-indigo-400 hover:text-indigo-300"
          >
            + SMA cross
          </button>
        )}
      </div>

      <div className="space-y-2">
        {leaves.map((leaf, i) => (
          <LeafRow
            key={i}
            leaf={leaf}
            onChange={(next) => emit(leaves.map((l, j) => (j === i ? next : l)))}
            onRemove={() => emit(leaves.filter((_, j) => j !== i))}
            readOnly={readOnly}
          />
        ))}
      </div>

      {!readOnly && (
        <button
          type="button"
          onClick={() => emit([...leaves, { ...EMPTY_LEAF }])}
          className="text-sm text-indigo-700 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300"
        >
          + Add condition
        </button>
      )}
    </div>
  );
}
