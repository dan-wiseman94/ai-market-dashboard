import type { Leaf, Metric, Op, Window, IndicatorParams } from "@/api/triggers";
import { describeLeaf } from "@/lib/triggers/describe";

const METRICS: { value: Metric; label: string }[] = [
  { value: "price", label: "price" },
  { value: "pct_change", label: "pct_change" },
  { value: "volume_z", label: "volume_z" },
  { value: "vix", label: "vix" },
  { value: "position_pl", label: "position_pl" },
  { value: "position_pl_pct", label: "position_pl_pct" },
  { value: "rsi", label: "rsi" },
  { value: "sma_spread_pct", label: "sma_spread_pct" },
  { value: "atr_pct", label: "atr_pct" },
  { value: "dist_from_sma_pct", label: "dist_from_sma_pct" },
  { value: "dist_from_52w_high", label: "dist_from_52w_high" },
  { value: "dist_from_52w_low", label: "dist_from_52w_low" },
  { value: "gap_pct", label: "gap_pct" },
];

const OPS: Op[] = [">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"];
const WINDOWS: Window[] = ["1m", "5m", "15m", "1h", "1d"];

const TICKER_METRICS: Metric[] = [
  "price", "pct_change", "volume_z",
  "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
  "dist_from_52w_high", "dist_from_52w_low", "gap_pct",
];

// Metrics that require a window selector (excludes daily-only)
const WINDOW_METRICS: Metric[] = ["pct_change", "volume_z", "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct"];

// Indicator metrics that expose a params sub-form
const INDICATOR_METRICS: Metric[] = [
  "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
  "dist_from_52w_high", "dist_from_52w_low", "gap_pct",
];

const PERIOD_METRICS: Metric[] = ["rsi", "atr_pct", "dist_from_sma_pct"];

const FAST_SLOW_METRICS: Metric[] = ["sma_spread_pct"];

function needsTicker(m: Metric): boolean {
  return TICKER_METRICS.includes(m);
}
function needsWindow(m: Metric): boolean {
  return WINDOW_METRICS.includes(m);
}
function needsParams(m: Metric): boolean {
  return INDICATOR_METRICS.includes(m);
}

export interface LeafRowProps {
  leaf: Leaf;
  onChange: (next: Leaf) => void;
  onRemove: () => void;
  readOnly?: boolean;
}

export default function LeafRow({ leaf, onChange, onRemove, readOnly }: LeafRowProps) {
  function patch(p: Partial<Leaf>) {
    let next: Leaf = { ...leaf, ...p };
    // Normalize when metric changes: drop fields that no longer apply.
    if (p.metric && p.metric !== leaf.metric) {
      if (!needsTicker(p.metric)) delete (next as Partial<Leaf>).ticker;
      else if (!leaf.ticker) next = { ...next, ticker: "SPY" };
      if (!needsWindow(p.metric)) delete (next as Partial<Leaf>).window;
      else if (!leaf.window) next = { ...next, window: "5m" };
      if (!needsParams(p.metric)) delete (next as Partial<Leaf>).params;
    }
    onChange(next);
  }

  function patchParam(key: keyof IndicatorParams, rawVal: string) {
    const val = parseInt(rawVal, 10);
    if (isNaN(val)) return;
    onChange({ ...leaf, params: { ...(leaf.params ?? {}), [key]: val } });
  }

  const params = leaf.params ?? {};
  const showPeriod = PERIOD_METRICS.includes(leaf.metric);
  const showFastSlow = FAST_SLOW_METRICS.includes(leaf.metric);

  return (
    <div className="border-l-4 border-indigo-500 pl-3 py-2 bg-neutral-900 rounded">
      <div className="flex gap-2 items-center flex-wrap">
        <select
          aria-label="metric"
          value={leaf.metric}
          onChange={(e) => patch({ metric: e.target.value as Metric })}
          className="bg-neutral-800 px-2 py-1 rounded"
          disabled={readOnly}
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
            readOnly={readOnly}
          />
        )}

        <select
          aria-label="operator"
          value={leaf.op}
          onChange={(e) => patch({ op: e.target.value as Op })}
          className="bg-neutral-800 px-2 py-1 rounded"
          disabled={readOnly}
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
          readOnly={readOnly}
        />

        {needsWindow(leaf.metric) && (
          <select
            aria-label="window"
            value={leaf.window ?? "5m"}
            onChange={(e) => patch({ window: e.target.value as Window })}
            className="bg-neutral-800 px-2 py-1 rounded"
            disabled={readOnly}
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        )}

        {!readOnly && (
          <button
            type="button"
            aria-label="remove condition"
            onClick={onRemove}
            className="text-neutral-500 hover:text-rose-700 dark:hover:text-rose-400 ml-auto"
          >
            ✕
          </button>
        )}
      </div>

      {needsParams(leaf.metric) && !readOnly && (
        <div className="flex gap-3 mt-2 items-center text-xs text-neutral-400">
          {showPeriod && (
            <label className="flex items-center gap-1">
              <span>period</span>
              <input
                aria-label="period"
                type="number"
                min={2}
                max={400}
                value={params.period ?? 14}
                onChange={(e) => patchParam("period", e.target.value)}
                className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
              />
            </label>
          )}
          {showFastSlow && (
            <>
              <label className="flex items-center gap-1">
                <span>fast</span>
                <input
                  aria-label="fast period"
                  type="number"
                  min={2}
                  max={400}
                  value={params.fast ?? 50}
                  onChange={(e) => patchParam("fast", e.target.value)}
                  className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
                />
              </label>
              <label className="flex items-center gap-1">
                <span>slow</span>
                <input
                  aria-label="slow period"
                  type="number"
                  min={3}
                  max={600}
                  value={params.slow ?? 200}
                  onChange={(e) => patchParam("slow", e.target.value)}
                  className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
                />
              </label>
            </>
          )}
        </div>
      )}

      <div className="text-xs text-neutral-400 mt-1">{describeLeaf(leaf)}</div>
    </div>
  );
}
