import { useState } from "react";
import { useErrors, useResolveError } from "@/hooks/useErrors";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { RelativeTime } from "@/components/RelativeTime";

function levelBadge(level: string): string {
  switch (level) {
    case "critical":
      return "font-mono text-[10px] uppercase tracking-loose2 px-1.5 py-0.5 rounded-ledger border border-loss-300 text-loss-300 bg-loss-300/10";
    case "error":
      return "font-mono text-[10px] uppercase tracking-loose2 px-1.5 py-0.5 rounded-ledger border border-loss-400 text-loss-400 bg-loss-400/10";
    case "warning":
      return "font-mono text-[10px] uppercase tracking-loose2 px-1.5 py-0.5 rounded-ledger border border-copper-400 text-copper-400 bg-copper-400/10";
    default:
      return "font-mono text-[10px] uppercase tracking-loose2 px-1.5 py-0.5 rounded-ledger border border-ink-500 text-ink-500 bg-ink-500/10";
  }
}

export default function ErrorsPage() {
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const { data, isLoading } = useErrors(unresolvedOnly);
  const resolve = useResolveError();

  if (isLoading) {
    return (
      <main className="px-8 py-8 max-w-4xl mx-auto">
        <SkeletonRows rows={5} />
      </main>
    );
  }

  const errors = data?.results ?? [];

  return (
    <main className="px-8 py-8 max-w-4xl mx-auto ledger-fade-in space-y-6">
      <header className="pb-5 border-b border-rule flex items-center justify-between">
        <div>
          <span className="ledger-eyebrow">System</span>
          <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
            Errors
          </h1>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-400 cursor-pointer select-none">
          <input
            type="checkbox"
            className="accent-copper-400"
            checked={unresolvedOnly}
            onChange={(e) => setUnresolvedOnly(e.target.checked)}
            aria-label="Unresolved only"
          />
          Unresolved only
        </label>
      </header>

      {errors.length === 0 ? (
        <EmptyState
          title="No errors"
          body={
            unresolvedOnly
              ? "No unresolved errors. All clear."
              : "No errors recorded yet."
          }
        />
      ) : (
        <ul className="space-y-2">
          {errors.map((row) => (
            <li
              key={row.id}
              className="rounded-ledger border border-rule bg-ink-900 px-4 py-3 flex items-start gap-4"
            >
              <span className={levelBadge(row.level)} aria-label={`level: ${row.level}`}>
                {row.level}
              </span>

              <div className="flex-1 min-w-0">
                <span className="font-mono text-xs text-ink-400 mr-2">
                  {row.source}
                </span>
                <p className="text-sm text-ink-200 mt-0.5 break-words">
                  {row.message}
                </p>
              </div>

              <div className="flex flex-col items-end gap-2 shrink-0">
                <span className="text-xs text-ink-500 font-mono">
                  <RelativeTime iso={row.created_at} suffix=" ago" />
                </span>
                <button
                  type="button"
                  disabled={row.resolved || resolve.isPending}
                  onClick={() => resolve.mutate(row.id)}
                  className="text-xs px-2 py-0.5 rounded-ledger border border-rule text-ink-400 hover:text-copper-300 hover:border-copper-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {row.resolved ? "Resolved" : "Resolve"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
