import { useState } from "react";
import { Link } from "react-router-dom";
import { useThreadsPage } from "@/hooks/useThread";
import { RelativeTime } from "@/components/RelativeTime";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

const PAGE = 50;

export default function ThreadsPage() {
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const { data, isLoading } = useThreadsPage({ limit: PAGE, offset });

  const rows = data?.results ?? [];
  const count = data?.count ?? 0;
  const q = query.trim().toLowerCase();
  // Page-local filter: narrows the currently-loaded page; Next/Prev reach the rest.
  const threads = q
    ? rows.filter(
        (t) =>
          (t.title || "").toLowerCase().includes(q) ||
          t.kind.toLowerCase().includes(q) ||
          (t.profile?.name ?? "").toLowerCase().includes(q),
      )
    : rows;

  function renderBody() {
    if (isLoading) return <SkeletonRows rows={4} />;
    if (rows.length === 0) {
      return (
        <EmptyState
          title="No threads yet"
          body="Capture a snapshot and pin it to start a consultation."
        />
      );
    }
    if (threads.length === 0) {
      return <EmptyState title="No matches" body={`No threads on this page match “${query}”.`} />;
    }
    return (
      <ul className="space-y-1">
        {threads.map((t) => (
          <li key={t.id} data-testid={`thread-row-${t.id}`} className="p-3 rounded border border-rule flex justify-between">
            <Link to={`/threads/${t.id}`} className="hover:underline">
              <div className="font-medium">{t.title || `Thread #${t.id}`}</div>
              <div className="text-xs text-ink-500">
                {t.kind} · {t.profile?.name ?? "no profile"} · <RelativeTime iso={t.created_at} suffix=" ago" />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    );
  }

  const start = count === 0 ? 0 : offset + 1;
  const end = Math.min(offset + PAGE, count);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE < count;

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Threads</h1>
        <Link to="/snapshot" className="px-3 py-1 rounded bg-gain-500 hover:bg-gain-400 text-sm">
          + Snapshot
        </Link>
      </div>

      <input
        aria-label="Filter"
        type="search"
        placeholder="Filter by title, kind, or profile…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full rounded border border-rule px-3 py-2 text-sm"
      />

      {renderBody()}

      {count > PAGE && (
        <div className="flex items-center justify-between text-sm text-ink-500">
          <span>
            {start}–{end} of {count}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
              className="rounded border border-rule px-3 py-1 disabled:opacity-40 hover:text-copper-300"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => setOffset(offset + PAGE)}
              className="rounded border border-rule px-3 py-1 disabled:opacity-40 hover:text-copper-300"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
