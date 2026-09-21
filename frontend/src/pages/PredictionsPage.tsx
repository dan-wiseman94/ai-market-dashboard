import { useState } from "react";

import {
  PREDICTION_STATUSES,
  type AIPrediction,
  type PredictionCounts,
  type PredictionQuery,
  type PredictionStatus,
  type PredictionTickerStats,
} from "@/api/predictions";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { usePredictionLedger, usePredictionStats } from "@/hooks/usePredictions";

/* ── Honest nulls ──────────────────────────────────────────────────────────────
 * `hit_rate` and `avg_forward_return_pct` come back null when the cohort holds no
 * decisive calls (mixed / inconclusive are not scored either way). Null is NOT
 * zero — a 0% hit rate means "every decisive call was wrong", which is a very
 * different statement from "nothing has resolved yet". Both render as an em dash
 * with a stated reason.
 * ────────────────────────────────────────────────────────────────────────────── */
const NO_DATA = "—";
const NO_DECISIVE = "No decisive calls yet";

function formatHitRate(value: number | null): string {
  return value === null ? NO_DATA : `${(value * 100).toFixed(0)}%`;
}

function formatReturn(value: number | null): string {
  return value === null ? NO_DATA : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function returnTone(value: number | null): string {
  if (value === null) return "text-ink/60";
  if (value > 0) return "text-emerald-700 dark:text-emerald-400";
  if (value < 0) return "text-red-700 dark:text-red-400";
  return "text-ink";
}

const DIRECTION_TONE: Record<string, string> = {
  bullish: "text-emerald-700 dark:text-emerald-400",
  bearish: "text-red-700 dark:text-red-400",
  neutral: "text-ink/70",
};

function StatTile({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <div className="rounded border border-rule p-3">
      <dt className="text-xs uppercase tracking-wide text-ink/60">{label}</dt>
      <dd className={`mt-1 text-xl font-semibold ${tone ?? "text-ink"}`}>{value}</dd>
      <p className="mt-1 text-[11px] text-ink/50">{hint}</p>
    </div>
  );
}

function StatsHeader({ totals }: { totals: PredictionCounts }) {
  const decisive = totals.correct + totals.incorrect;
  return (
    <dl className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="prediction-stats">
      <StatTile
        label="Hit rate"
        value={formatHitRate(totals.hit_rate)}
        hint={totals.hit_rate === null ? NO_DECISIVE : `${totals.correct}/${decisive} decisive`}
      />
      <StatTile
        label="Avg forward return"
        value={formatReturn(totals.avg_forward_return_pct)}
        tone={returnTone(totals.avg_forward_return_pct)}
        hint={
          totals.avg_forward_return_pct === null
            ? "Nothing has resolved yet"
            : "Across scored calls"
        }
      />
      <StatTile label="Open" value={String(totals.open)} hint="Awaiting their horizon" />
      <StatTile
        label="Resolved"
        value={String(totals.resolved)}
        hint={`${totals.invalidated} invalidated`}
      />
      <StatTile
        label="Total calls"
        value={String(totals.total)}
        hint={`${totals.mixed} mixed · ${totals.inconclusive} inconclusive`}
      />
    </dl>
  );
}

function ByTickerTable({ rows }: { rows: PredictionTickerStats[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="text-lg font-medium">By ticker</h2>
      <table className="mt-2 w-full text-sm">
        <caption className="sr-only">
          Prediction counts, hit rate and average forward return per ticker, busiest first
        </caption>
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-ink/60">
            <th scope="col" className="py-1">Ticker</th>
            <th scope="col" className="py-1 text-right">Calls</th>
            <th scope="col" className="py-1 text-right">Open</th>
            <th scope="col" className="py-1 text-right">Hit rate</th>
            <th scope="col" className="py-1 text-right">Avg fwd return</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {rows.map((row) => (
            <tr key={row.ticker} data-testid={`ticker-row-${row.ticker}`}>
              <th scope="row" className="py-1.5 text-left font-mono text-[12px] text-copper-400">
                {row.ticker}
              </th>
              <td className="py-1.5 text-right tabular-nums">{row.total}</td>
              <td className="py-1.5 text-right tabular-nums">{row.open}</td>
              <td className="py-1.5 text-right tabular-nums">
                {formatHitRate(row.hit_rate)}
                {row.hit_rate === null && <span className="sr-only">{NO_DECISIVE}</span>}
              </td>
              <td className={`py-1.5 text-right tabular-nums ${returnTone(row.avg_forward_return_pct)}`}>
                {formatReturn(row.avg_forward_return_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function LedgerRow({ p }: { p: AIPrediction }) {
  return (
    <li className="py-3" data-testid={`prediction-row-${p.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[12px] uppercase tracking-wide text-copper-400">
            {p.ticker}
          </span>
          <span className={`text-sm font-medium ${DIRECTION_TONE[p.direction] ?? "text-ink"}`}>
            {p.direction}
          </span>
          <span className="text-xs text-ink/60">
            {p.horizon_days}d · confidence {(p.confidence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-baseline gap-3 text-xs">
          <span className="text-ink/60">{p.status}</span>
          {p.status === "resolved" && (
            <span className="text-ink/80">
              {p.verdict}
              {" · "}
              <span className={returnTone(p.forward_return_pct)}>
                {formatReturn(p.forward_return_pct)}
              </span>
            </span>
          )}
          <span className="text-ink/50">{new Date(p.predicted_at).toLocaleDateString()}</span>
        </div>
      </div>
      {p.rationale && <p className="mt-1 text-sm text-ink/80">{p.rationale}</p>}
      <p className="mt-1 text-[11px] text-ink/50">
        {p.provider}
        {p.model ? ` · ${p.model}` : ""}
        {p.profile_name ? ` · ${p.profile_name}` : ""}
        {p.invalidation_note ? ` · invalidates if ${p.invalidation_note}` : ""}
      </p>
    </li>
  );
}

function LedgerFilters({
  query,
  onChange,
}: {
  query: PredictionQuery;
  onChange: (next: PredictionQuery) => void;
}) {
  return (
    <fieldset className="mt-4 flex flex-wrap items-end gap-3 rounded border border-rule p-3">
      <legend className="px-1 text-xs uppercase tracking-wide text-ink/60">Filters</legend>
      <label className="grid gap-1">
        <span className="text-[12px] text-ink/70">Ticker</span>
        <input
          type="text"
          value={query.ticker ?? ""}
          aria-describedby="predictions-filter-help"
          onChange={(e) => onChange({ ...query, ticker: e.target.value, page: 1 })}
          placeholder="e.g. NVDA"
          className="ledger-input w-32 py-1 font-mono text-[12px]"
        />
      </label>
      <label className="grid gap-1">
        <span className="text-[12px] text-ink/70">Status</span>
        <select
          value={query.status ?? ""}
          aria-describedby="predictions-filter-help"
          onChange={(e) => onChange({ ...query, status: e.target.value as PredictionStatus | "", page: 1 })}
          className="ledger-input py-1 text-[12px]"
        >
          <option value="">All</option>
          {PREDICTION_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1">
        <span className="text-[12px] text-ink/70">Horizon (days)</span>
        <input
          type="number"
          min={1}
          value={query.horizon ?? ""}
          aria-describedby="predictions-filter-help"
          onChange={(e) => onChange({ ...query, horizon: e.target.value, page: 1 })}
          placeholder="any"
          className="ledger-input w-24 py-1 text-[12px]"
        />
      </label>
      <p id="predictions-filter-help" className="text-[11px] text-ink/50">
        Filters apply to both the ledger and the stats above it.
      </p>
    </fieldset>
  );
}

export default function PredictionsPage() {
  const [query, setQuery] = useState<PredictionQuery>({ page: 1 });
  const { data: stats } = usePredictionStats(query);
  const { data: page, isLoading, isError } = usePredictionLedger(query);

  const rows = page?.results ?? [];
  const pageNumber = query.page ?? 1;

  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">Prediction ledger</h1>
      <p className="mt-1 text-sm text-ink/70">
        Every directional call the AI made, scored against what the market actually did.
      </p>

      {stats ? (
        <StatsHeader totals={stats.totals} />
      ) : (
        <div className="mt-4">
          <SkeletonRows rows={2} />
        </div>
      )}

      <LedgerFilters query={query} onChange={setQuery} />

      {isError ? (
        <EmptyState
          title="Could not load the ledger"
          body="The predictions endpoint did not answer. Retry in a moment."
        />
      ) : isLoading ? (
        <div className="mt-4">
          <SkeletonRows rows={5} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          title="No predictions match"
          body="Predictions are extracted automatically from structured observer runs. Widen the filters, or let a structured observer schedule fire."
        />
      ) : (
        <>
          <ul className="mt-4 divide-y divide-rule">
            {rows.map((p) => (
              <LedgerRow key={p.id} p={p} />
            ))}
          </ul>
          <nav className="mt-4 flex items-center gap-3" aria-label="Ledger pagination">
            <button
              type="button"
              className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
              disabled={!page?.previous}
              onClick={() => setQuery({ ...query, page: Math.max(1, pageNumber - 1) })}
            >
              Previous
            </button>
            <span className="text-xs text-ink/60">
              Page {pageNumber} · {page?.count ?? 0} calls
            </span>
            <button
              type="button"
              className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
              disabled={!page?.next}
              onClick={() => setQuery({ ...query, page: pageNumber + 1 })}
            >
              Next
            </button>
          </nav>
        </>
      )}

      {stats && <ByTickerTable rows={stats.by_ticker} />}
    </main>
  );
}
