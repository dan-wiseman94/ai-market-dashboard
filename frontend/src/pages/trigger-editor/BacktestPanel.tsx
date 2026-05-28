import type { UseMutationResult } from "@tanstack/react-query";
import type { BacktestMatch } from "@/api/triggers";

type BacktestResult = { match_count: number; matches: BacktestMatch[] };

export interface BacktestPanelProps {
  start: string;
  onStartChange: (value: string) => void;
  end: string;
  onEndChange: (value: string) => void;
  backtest: UseMutationResult<BacktestResult, Error, void>;
  result: BacktestResult | null;
}

export default function BacktestPanel({
  start, onStartChange, end, onEndChange, backtest, result,
}: BacktestPanelProps) {
  return (
    <div className="space-y-3">
      <div className="text-sm text-neutral-400">
        Replay the current condition against stored OHLC bars. Only <code>price</code> and
        <code>pct_change</code> leaves evaluate; live-only metrics are skipped.
      </div>
      <div className="flex gap-3 items-end">
        <label className="text-sm">
          <div className="text-neutral-400 mb-1">Start</div>
          <input type="date" value={start} onChange={(e) => onStartChange(e.target.value)}
                 className="bg-neutral-800 px-3 py-2 rounded" />
        </label>
        <label className="text-sm">
          <div className="text-neutral-400 mb-1">End</div>
          <input type="date" value={end} onChange={(e) => onEndChange(e.target.value)}
                 className="bg-neutral-800 px-3 py-2 rounded" />
        </label>
        <button
          type="button"
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
          onClick={() => backtest.mutate()}
          disabled={backtest.isPending}
        >{backtest.isPending ? "Running…" : "Run backtest"}</button>
      </div>
      {backtest.isError && (
        <div className="text-rose-700 dark:text-rose-400 text-sm">
          {(backtest.error as Error)?.message ?? "Backtest failed"}
        </div>
      )}
      {result && (
        <div className="space-y-1">
          <div className="text-sm">
            <span className="font-mono">{result.match_count}</span>
            <span className="text-neutral-400"> matches</span>
          </div>
          <ul className="text-xs font-mono text-neutral-300 max-h-60 overflow-auto">
            {result.matches.slice(0, 50).map((m, i) => (
              <li key={i}>
                {new Date(m.ts).toLocaleDateString()} —
                {Object.entries(m.values).filter(([k]) => !k.startsWith("_prior:"))
                  .map(([k, v]) => ` ${k}=${v ?? "—"}`).join("")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
