import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { useCurrentBook } from "@/hooks/useBook";

export default function BookPage() {
  const { data: book, isLoading } = useCurrentBook();
  if (isLoading) return <Skeleton where="book-page" />;
  if (!book) {
    return (
      <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
        <EmptyState title="No book snapshot yet" body="The book X-ray has not run. Trigger a recompute or wait for the daily snapshot." />
      </div>
    );
  }
  const c = book.concentration;
  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">Book risk X-ray</h1>
      {book.narrative && <p className="mt-2 text-ink/80">{book.narrative}</p>}

      <h2 className="mt-6 text-lg font-medium">Concentration</h2>
      <p className="mt-1 text-sm text-ink/70">
        HHI {c.hhi?.toFixed(2)} · top-N share {c.top_n_share != null ? `${(c.top_n_share * 100).toFixed(0)}%` : "—"} ·
        net long {c.net_long} / net short {c.net_short}
      </p>

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
          <li key={cl.members.join(",")} title={cl.members.join(", ")}>
            {cl.members.length} ticker{cl.members.length !== 1 ? "s" : ""}{" "}
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
            <span className={e.net_signed >= 0 ? "text-emerald-600" : "text-copper"}>
              {e.net_signed > 0 ? "+" : ""}
              {e.net_signed}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
