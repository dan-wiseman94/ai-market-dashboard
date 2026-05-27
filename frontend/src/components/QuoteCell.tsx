import type { Quote } from "@/api/market";

export default function QuoteCell({ q }: { q: Quote | undefined }) {
  if (!q || q.last === null) return <span className="text-slate-500">—</span>;
  const up = (q.pct_change ?? 0) >= 0;
  const pct = q.pct_change === null ? "" : `${up ? "+" : ""}${q.pct_change.toFixed(2)}%`;
  return (
    <span className="tabular-nums">
      <span>{q.last.toFixed(2)}</span>
      <span className={`ml-2 text-xs ${up ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>{pct}</span>
    </span>
  );
}
