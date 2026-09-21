import { useId, useState } from "react";

import type { BookSnapshotTrend } from "@/api/book";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useBookHistory } from "@/hooks/useBook";
import { fmt, usd } from "@/utils/format";

const WINDOWS = [30, 90, 365] as const;

/** A missing metric is a gap in the record, not a zero — render it as one. */
function num(v: number | null, digits = 2): string {
  return v == null ? "—" : fmt(v, digits);
}
function pct(v: number | null): string {
  return v == null ? "—" : `${(v * 100).toFixed(0)}%`;
}
function money(v: number | null): string {
  return v == null ? "—" : usd(v, 0);
}

function HistoryRow({ row }: { row: BookSnapshotTrend }) {
  return (
    <tr className="border-b border-rule">
      <th scope="row" className="py-2 text-left font-mono font-normal text-ink-200">
        {row.as_of_date}
      </th>
      <td className="py-2 text-right tabular-nums">{row.position_count}</td>
      <td className="py-2 text-right tabular-nums">{num(row.hhi)}</td>
      <td className="py-2 text-right tabular-nums">{pct(row.top_n_share)}</td>
      <td className="py-2 text-right tabular-nums">{money(row.gross_dollar)}</td>
      <td className="py-2 text-right tabular-nums">{money(row.net_dollar)}</td>
      <td className="py-2 text-right tabular-nums">{money(row.diversified_var_usd)}</td>
      <td className="py-2 text-right text-ink-400">{row.alignment ?? "—"}</td>
    </tr>
  );
}

/**
 * The book's trend over time.
 *
 * `GET /api/book/` serves flattened scalars (not the full X-ray), newest first,
 * so this table reads them straight through. Every metric is nullable.
 */
export default function BookHistoryTable() {
  const [limit, setLimit] = useState<number>(30);
  const { data, isLoading, isError } = useBookHistory(limit);
  const selectId = useId();

  return (
    <section className="mt-8">
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-lg font-medium">History</h2>
        <div className="flex items-center gap-2">
          <label htmlFor={selectId} className="text-xs uppercase tracking-wide text-ink-400">
            Window
          </label>
          <select
            id={selectId}
            className="rounded border border-rule bg-ink-850 px-2 py-1 text-sm"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{`Last ${w} readings`}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <div className="mt-3"><SkeletonRows rows={4} /></div>}
      {!isLoading && isError && (
        <p className="mt-3 text-sm text-loss">Book history could not be loaded.</p>
      )}
      {!isLoading && !isError && (data ?? []).length === 0 && (
        <EmptyState
          title="No earlier readings"
          body="The book snapshots once a day. Past readings appear here from tomorrow."
        />
      )}
      {!isLoading && !isError && (data ?? []).length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Daily book readings, newest first: concentration, exposure and Value-at-Risk.
            </caption>
            <thead>
              <tr className="border-b border-rule text-ink-400">
                <th scope="col" className="pb-2 text-left">Date</th>
                <th scope="col" className="pb-2 text-right">Positions</th>
                <th scope="col" className="pb-2 text-right">HHI</th>
                <th scope="col" className="pb-2 text-right">Top-N</th>
                <th scope="col" className="pb-2 text-right">Gross</th>
                <th scope="col" className="pb-2 text-right">Net</th>
                <th scope="col" className="pb-2 text-right">VaR (div.)</th>
                <th scope="col" className="pb-2 text-right">Regime fit</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((row) => <HistoryRow key={row.id} row={row} />)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
