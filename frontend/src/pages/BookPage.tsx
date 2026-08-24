import { ConveneWarRoomButton } from "@/components/ConveneWarRoomButton";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useCurrentBook, useRecomputeBook } from "@/hooks/useBook";
import { plClass, signed, usd } from "@/utils/format";

function RecomputeBookButton() {
  const recompute = useRecomputeBook();
  return (
    <button
      type="button"
      disabled={recompute.isPending}
      className="rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
      onClick={() => recompute.mutate()}
    >
      {recompute.isPending ? "Recomputing…" : "Recompute"}
    </button>
  );
}

export default function BookPage() {
  const { data: book, isLoading } = useCurrentBook();
  if (isLoading) return <Skeleton where="book-page" />;
  if (!book) {
    return (
      <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
        <EmptyState title="No book snapshot yet" body="The book X-ray has not run. Trigger a recompute or wait for the daily snapshot." />
        <div className="mt-4">
          <RecomputeBookButton />
        </div>
      </div>
    );
  }
  const c = book.concentration;
  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Book risk X-ray</h1>
        <div className="flex items-center gap-2">
          <RecomputeBookButton />
          <ConveneWarRoomButton subject={{ book_snapshot_id: book.id }} />
        </div>
      </div>
      {book.narrative && <p className="mt-2 text-ink/80">{book.narrative}</p>}

      <h2 className="mt-6 text-lg font-medium">Concentration</h2>
      <p className="mt-1 text-sm text-ink/70">
        HHI {c.hhi?.toFixed(2)} · top-N share {c.top_n_share != null ? `${(c.top_n_share * 100).toFixed(0)}%` : "—"} ·
        net long {c.net_long} / net short {c.net_short}
      </p>

      {book.var_beta?.available ? (
        <>
          <h2 className="mt-6 text-lg font-medium">Value-at-Risk &amp; factor beta</h2>
          <p className="mt-1 text-sm text-ink/70" data-testid="book-var-summary">
            1-day 95% VaR{" "}
            <span className="font-medium">{usd(book.var_beta.portfolio.diversified_var_usd, 0)}</span>{" "}
            diversified vs {usd(book.var_beta.portfolio.undiversified_var_usd, 0)} undiversified —{" "}
            {usd(book.var_beta.portfolio.diversification_benefit_usd, 0)} diversification benefit. Net
            $SPX-equivalent exposure {usd(book.var_beta.portfolio.beta_adjusted_net_exposure_usd, 0)}.
            {book.var_beta.skipped ? ` (${book.var_beta.skipped} unpriced.)` : ""}
          </p>
          <ul className="mt-2 divide-y divide-rule">
            {book.var_beta.positions.map((q) => (
              <li key={q.ticker} className="flex justify-between py-2 text-sm">
                <span>
                  {q.ticker} <span className="text-ink/50">β {q.beta ?? "—"}</span>
                </span>
                <span className="text-ink/70">
                  VaR {usd(q.var_usd, 0)} · vol {q.daily_vol_pct}%
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        book.var_beta?.note && (
          <p className="mt-6 text-sm text-ink/50">Value-at-Risk: {book.var_beta.note}</p>
        )
      )}

      <h2 className="mt-6 text-lg font-medium">Regime fit</h2>
      <p className="mt-1 text-sm">
        <span className={book.regime_fit.alignment === "misaligned" ? "text-copper" : "text-ink"}>
          {book.regime_fit.alignment}
        </span>{" "}
        — {book.regime_fit.note}
      </p>

      <h2 className="mt-6 text-lg font-medium">Correlation clusters</h2>
      <ul className="mt-2 list-disc pl-5">
        {book.clusters.length === 0 && <li className="text-ink/60">No clusters detected.</li>}
        {book.clusters.map((cl) => (
          <li key={cl.members.join(",")}>
            {cl.members.join(", ")}{" "}
            {cl.avg_corr != null && <span className="text-ink/60">(ρ≈{cl.avg_corr.toFixed(2)})</span>}
          </li>
        ))}
      </ul>

      <h2 className="mt-6 text-lg font-medium">Exposures</h2>
      <ul className="mt-2 divide-y divide-rule">
        {book.exposures.map((e) => (
          <li key={e.ticker} className="flex justify-between py-2 text-sm">
            <span>
              {e.ticker} <span className="text-ink/50">({e.sources.join("+")})</span>
            </span>
            <span className={plClass(e.net_signed)}>
              {signed(e.net_signed, 0)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
