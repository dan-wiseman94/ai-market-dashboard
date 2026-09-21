import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useCoverageIndex, type CoverageListRow, type Stance } from "@/hooks/useCoverage";
import { convictionLabel, STANCE_LABEL, STANCE_TONE } from "@/lib/coverageStance";

type StanceFilter = Stance | "all";

const STANCE_FILTERS: Array<{ value: StanceFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "bull", label: "Bullish" },
  { value: "bear", label: "Bearish" },
  { value: "neutral", label: "Neutral" },
];

type SortKey = "ticker" | "conviction" | "updated";

const SORTS: Array<{ value: SortKey; label: string }> = [
  { value: "updated", label: "Recently revised" },
  { value: "conviction", label: "Conviction" },
  { value: "ticker", label: "Ticker" },
];

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function sortRows(rows: CoverageListRow[], key: SortKey): CoverageListRow[] {
  const out = [...rows];
  if (key === "ticker") return out.sort((a, b) => a.ticker.localeCompare(b.ticker));
  if (key === "conviction") return out.sort((a, b) => b.conviction - a.conviction);
  return out.sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

function CoverageRow({ row }: { row: CoverageListRow }) {
  return (
    <li data-testid={`coverage-row-${row.ticker}`}>
      <Link
        to={`/coverage/${row.ticker}`}
        className="flex flex-wrap items-baseline gap-x-4 gap-y-1 rounded border border-rule p-3 transition-colors hover:border-copper-700"
      >
        <span className="w-16 font-mono text-sm text-ink-100">{row.ticker}</span>
        <span className={`text-sm font-medium ${STANCE_TONE[row.stance]}`}>
          {STANCE_LABEL[row.stance]}
        </span>
        <span className="text-sm text-ink-400">
          conviction {convictionLabel(row.conviction)}
        </span>
        <span className="text-xs text-ink-500">
          {row.revision_count} {row.revision_count === 1 ? "revision" : "revisions"}
        </span>
        <span className="ml-auto text-xs text-ink-500">
          updated {fmtDate(row.updated_at)}
        </span>
      </Link>
    </li>
  );
}

export default function CoverageIndexPage() {
  const { data, isLoading, isError } = useCoverageIndex();
  const [stance, setStance] = useState<StanceFilter>("all");
  const [sort, setSort] = useState<SortKey>("updated");

  const rows = useMemo(() => {
    const all = data ?? [];
    const filtered = stance === "all" ? all : all.filter((r) => r.stance === stance);
    return sortRows(filtered, sort);
  }, [data, stance, sort]);

  return (
    <main className="mx-auto max-w-4xl space-y-5 p-6 ledger-fade-in">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink-100">Coverage</h1>
        <p className="max-w-2xl text-sm text-ink-400">
          The house view on every name the desk covers — a standing note per ticker,
          revised with a reason rather than re-derived each snapshot. Open one for its
          bull and bear case, key levels, and revision history.
        </p>
      </header>

      <fieldset className="flex flex-wrap items-end gap-4 rounded border border-rule p-3">
        <legend className="px-1 text-xs uppercase tracking-wide text-ink-500">
          Filter and sort
        </legend>
        <label className="flex flex-col gap-1 text-xs text-ink-400">
          Stance
          <select
            value={stance}
            onChange={(e) => setStance(e.target.value as StanceFilter)}
            className="rounded border border-rule bg-transparent px-2 py-1 text-sm text-ink-200"
          >
            {STANCE_FILTERS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-400">
          Sort by
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded border border-rule bg-transparent px-2 py-1 text-sm text-ink-200"
          >
            {SORTS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      {isLoading ? (
        <SkeletonRows rows={5} />
      ) : isError ? (
        <EmptyState
          title="Couldn’t load coverage"
          body="The coverage index didn’t answer. Retry in a moment."
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={stance === "all" ? "No tickers covered yet" : "No tickers with that stance"}
          body={
            stance === "all"
              ? "An observer fire opens the first house view on a snapshot’s primary ticker. You can also open one by hand from a ticker’s market page."
              : "Clear the stance filter to see the rest of the book."
          }
        />
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <CoverageRow key={row.id} row={row} />
          ))}
        </ul>
      )}
    </main>
  );
}
