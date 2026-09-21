import { useState } from "react";

import type { Briefing } from "@/api/briefing";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useBriefings } from "@/hooks/useBriefing";
import { formatRelative } from "@/utils/format";

const PAGE_SIZE = 20;

function dayOf(b: Briefing): string {
  return b.scheduled_date ?? b.created_at.slice(0, 10);
}

function tone(status: string): "gain" | "loss" | undefined {
  if (status === "ready") return "gain";
  if (status === "failed") return "loss";
  return undefined;
}

function HistoryRow({
  briefing, selected, onSelect,
}: {
  briefing: Briefing;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-rule py-2">
      <div className="min-w-0">
        <span className="font-mono text-sm text-ink-200">{dayOf(briefing)}</span>
        <span className="ml-2 text-xs text-muted">{formatRelative(briefing.created_at)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="ledger-pill" data-tone={tone(briefing.status)}>{briefing.status}</span>
        <button
          type="button"
          aria-pressed={selected}
          className="rounded border border-rule px-2 py-0.5 text-xs text-ink-300 hover:text-copper-300"
          onClick={onSelect}
        >
          {selected ? `Viewing briefing from ${dayOf(briefing)}` : `View briefing from ${dayOf(briefing)}`}
        </button>
      </div>
    </li>
  );
}

/**
 * Past briefings, newest first, with drill-in.
 *
 * `GET /api/briefings/` returns whole `BriefingRun` rows (data included), so a
 * selected row can be handed straight back to the page's sections — no second
 * fetch, no detail route.
 */
export default function BriefingHistoryList({
  selectedId, onSelect,
}: {
  selectedId: number | null;
  onSelect: (b: Briefing | null) => void;
}) {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useBriefings(page);

  if (isLoading) return <SkeletonRows rows={3} />;
  if (isError || !data) {
    return <p className="text-sm text-loss">Briefing history could not be loaded.</p>;
  }
  if (data.count === 0) {
    return <EmptyState title="No past briefings" body="Briefings appear here once one has run." />;
  }

  const from = (page - 1) * PAGE_SIZE + 1;
  const to = from + data.results.length - 1;

  return (
    <div>
      <ul className="text-sm">
        {data.results.map((b) => (
          <HistoryRow
            key={b.id}
            briefing={b}
            selected={b.id === selectedId}
            onSelect={() => onSelect(b.id === selectedId ? null : b)}
          />
        ))}
      </ul>
      <div className="mt-3 flex items-center gap-3 text-xs text-ink-400">
        <button
          type="button"
          className="rounded border border-rule px-2 py-0.5 disabled:opacity-40"
          disabled={!data.previous}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Previous page
        </button>
        <button
          type="button"
          className="rounded border border-rule px-2 py-0.5 disabled:opacity-40"
          disabled={!data.next}
          onClick={() => setPage((p) => p + 1)}
        >
          Next page
        </button>
        <span>{`${from}–${to} of ${data.count}`}</span>
      </div>
    </div>
  );
}
