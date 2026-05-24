import type { Leaf, Metric, Op, Window } from "@/api/triggers";
import { describeLeaf } from "@/lib/triggers/describe";

const METRICS: { value: Metric; label: string }[] = [
  { value: "price", label: "price" },
  { value: "pct_change", label: "pct_change" },
  { value: "volume_z", label: "volume_z" },
  { value: "vix", label: "vix" },
  { value: "position_pl", label: "position_pl" },
  { value: "position_pl_pct", label: "position_pl_pct" },
];

const OPS: Op[] = [">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"];
const WINDOWS: Window[] = ["1m", "5m", "15m", "1h", "1d"];

function needsTicker(m: Metric): boolean {
  return m === "price" || m === "pct_change" || m === "volume_z";
}
function needsWindow(m: Metric): boolean {
  return m === "pct_change" || m === "volume_z";
}

export interface LeafRowProps {
  leaf: Leaf;
  onChange: (next: Leaf) => void;
  onRemove: () => void;
}

export default function LeafRow({ leaf, onChange, onRemove }: LeafRowProps) {
  function patch(p: Partial<Leaf>) {
    let next: Leaf = { ...leaf, ...p };
    // Normalize when metric changes: drop fields that no longer apply.
    if (p.metric && p.metric !== leaf.metric) {
      if (!needsTicker(p.metric)) delete (next as Partial<Leaf>).ticker;
      else if (!leaf.ticker) next = { ...next, ticker: "SPY" };
      if (!needsWindow(p.metric)) delete (next as Partial<Leaf>).window;
      else if (!leaf.window) next = { ...next, window: "5m" };
    }
    onChange(next);
  }

  return (
    <div className="border-l-4 border-indigo-500 pl-3 py-2 bg-neutral-900 rounded">
      <div className="flex gap-2 items-center">
        <select
          aria-label="metric"
          value={leaf.metric}
          onChange={(e) => patch({ metric: e.target.value as Metric })}
          className="bg-neutral-800 px-2 py-1 rounded"
        >
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>

        {needsTicker(leaf.metric) && (
          <input
            aria-label="ticker"
            value={leaf.ticker ?? ""}
            onChange={(e) => patch({ ticker: e.target.value.toUpperCase() })}
            className="bg-neutral-800 px-2 py-1 rounded w-20"
          />
        )}

        <select
          aria-label="operator"
          value={leaf.op}
          onChange={(e) => patch({ op: e.target.value as Op })}
          className="bg-neutral-800 px-2 py-1 rounded"
        >
          {OPS.map((op) => (
            <option key={op} value={op}>{op}</option>
          ))}
        </select>

        <input
          aria-label="value"
          type="number"
          step="any"
          value={leaf.value}
          onChange={(e) => patch({ value: parseFloat(e.target.value) })}
          className="bg-neutral-800 px-2 py-1 rounded w-24"
        />

        {needsWindow(leaf.metric) && (
          <select
            aria-label="window"
            value={leaf.window ?? "5m"}
            onChange={(e) => patch({ window: e.target.value as Window })}
            className="bg-neutral-800 px-2 py-1 rounded"
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        )}

        <button
          type="button"
          aria-label="remove condition"
          onClick={onRemove}
          className="text-neutral-500 hover:text-rose-400 ml-auto"
        >
          ✕
        </button>
      </div>
      <div className="text-xs text-neutral-400 mt-1">{describeLeaf(leaf)}</div>
    </div>
  );
}
