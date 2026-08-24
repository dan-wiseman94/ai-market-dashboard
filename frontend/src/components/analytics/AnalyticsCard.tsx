import type { ReactNode } from "react";
import { SkeletonRows } from "@/components/Skeleton";

interface AnalyticsCardProps<T> {
  testid: string;
  title: string;
  /** Span two grid columns (the wider charts). */
  wide?: boolean;
  /** Always-visible controls (inputs/filters) rendered above the query states. */
  controls?: ReactNode;
  query: { isLoading: boolean; error: Error | null; data: T | undefined };
  children: (data: T) => ReactNode;
}

/** Shared shell for the analytics cards: surface + eyebrow header + optional
 *  controls + the loading/error states, rendering `children(data)` only once
 *  data has loaded. Each card supplies just its title, testid, query, and body. */
export function AnalyticsCard<T>({
  testid,
  title,
  wide,
  controls,
  query,
  children,
}: AnalyticsCardProps<T>) {
  return (
    <section data-testid={testid} className={`ledger-surface p-5${wide ? " md:col-span-2" : ""}`}>
      <header className="ledger-eyebrow mb-3">{title}</header>
      {controls}
      {query.isLoading && <SkeletonRows rows={3} />}
      {query.error && <p className="text-sm text-rose-700 dark:text-rose-400">{String(query.error)}</p>}
      {query.data && children(query.data)}
    </section>
  );
}
