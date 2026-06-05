import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useState } from "react";
import type { SnapshotListRow } from "@/api/snapshots";
import { fetchSnapshots } from "@/api/snapshots";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import SnapshotTable from "./snapshots/SnapshotTable";
import TickerTimeline from "./snapshots/TickerTimeline";
import CompareDrawer from "./snapshots/CompareDrawer";

type ViewMode = "table" | "timeline";

const VIEW_MODES: ViewMode[] = ["table", "timeline"];

function buildQueryParams(
  ticker: string,
  source: string,
  since: string,
  until: string,
): Record<string, string> {
  const params: Record<string, string> = {};
  if (ticker) params.ticker = ticker;
  if (source) params.source = source;
  if (since) params.since = since;
  if (until) params.until = until;
  return params;
}

function toggleSelection(prev: number[], id: number): number[] {
  if (prev.includes(id)) return prev.filter((x) => x !== id);
  if (prev.length >= 2) return [prev[1], id];
  return [...prev, id];
}

type FilterControlsProps = {
  ticker: string;
  source: string;
  since: string;
  until: string;
  setParam: (key: string, value: string) => void;
};

function FilterControls({ ticker, source, since, until, setParam }: FilterControlsProps) {
  return (
    <div className="flex flex-wrap gap-3 mb-4 items-end">
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Ticker
        <input
          type="text"
          value={ticker}
          onChange={(e) => setParam("ticker", e.target.value.toUpperCase())}
          placeholder="NVDA"
          className="px-2 py-1 rounded border border-rule bg-ink-900 text-ink-100 text-sm w-24 focus:border-copper-500 focus:outline-none"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Source
        <select
          value={source}
          onChange={(e) => setParam("source", e.target.value)}
          className="px-2 py-1 rounded border border-rule bg-ink-900 text-ink-100 text-sm w-32 focus:border-copper-500 focus:outline-none"
        >
          <option value="">All sources</option>
          <option value="manual">manual</option>
          <option value="observer">observer</option>
          <option value="trigger">trigger</option>
          <option value="briefing">briefing</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Since
        <input
          type="date"
          value={since}
          onChange={(e) => setParam("since", e.target.value)}
          className="px-2 py-1 rounded border border-rule bg-ink-900 text-ink-100 text-sm focus:border-copper-500 focus:outline-none"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Until
        <input
          type="date"
          value={until}
          onChange={(e) => setParam("until", e.target.value)}
          className="px-2 py-1 rounded border border-rule bg-ink-900 text-ink-100 text-sm focus:border-copper-500 focus:outline-none"
        />
      </label>
    </div>
  );
}

type ViewToggleBarProps = {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  selected: number[];
  onCompare: () => void;
};

function ViewToggleBar({ viewMode, setViewMode, selected, onCompare }: ViewToggleBarProps) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex gap-1 border border-rule rounded overflow-hidden">
        {VIEW_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setViewMode(mode)}
            className={[
              "px-3 py-1.5 text-xs font-mono capitalize transition-colors",
              viewMode === mode
                ? "bg-copper-900/40 text-copper-200"
                : "text-ink-400 hover:text-ink-100",
            ].join(" ")}
          >
            {mode}
          </button>
        ))}
      </div>
      {selected.length === 2 && (
        <button
          type="button"
          onClick={onCompare}
          className="px-3 py-1.5 text-xs rounded border border-copper-600 text-copper-200 hover:bg-copper-900/30 transition-colors"
        >
          Compare #{selected[0]} ↔ #{selected[1]}
        </button>
      )}
    </div>
  );
}

type SnapshotsContentProps = {
  isLoading: boolean;
  rows: SnapshotListRow[];
  viewMode: ViewMode;
  ticker: string;
  selected: number[];
  onToggle: (id: number) => void;
};

function SnapshotsContent({
  isLoading,
  rows,
  viewMode,
  ticker,
  selected,
  onToggle,
}: SnapshotsContentProps) {
  if (isLoading) {
    return <SkeletonRows rows={5} />;
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No snapshots yet"
        body="Capture a snapshot to start building your history."
      />
    );
  }
  if (viewMode === "table") {
    return <SnapshotTable rows={rows} selected={selected} onToggle={onToggle} />;
  }
  return <TickerTimeline ticker={ticker} />;
}

type CompareOverlayProps = {
  selected: number[];
  onClose: () => void;
};

function CompareOverlay({ selected, onClose }: CompareOverlayProps) {
  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-ink-950/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <CompareDrawer ids={[selected[0], selected[1]]} onClose={onClose} />
    </>
  );
}

export default function SnapshotsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [selected, setSelected] = useState<number[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Derive filter values from URL params (no setState in effect)
  const ticker = searchParams.get("ticker") ?? "";
  const source = searchParams.get("source") ?? "";
  const since = searchParams.get("since") ?? "";
  const until = searchParams.get("until") ?? "";

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      return next;
    });
  }

  const params = buildQueryParams(ticker, source, since, until);

  const { data, isLoading } = useQuery({
    queryKey: ["snapshots", params],
    queryFn: () => fetchSnapshots(params),
  });

  const rows = data?.results ?? [];

  function handleToggle(id: number) {
    setSelected((prev) => toggleSelection(prev, id));
  }

  function handleCompare() {
    if (selected.length === 2) setDrawerOpen(true);
  }

  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <header className="mb-6 pb-6 border-b border-rule">
        <span className="ledger-eyebrow">Snapshots</span>
        <h1
          className="ledger-display"
          style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}
        >
          Snapshot History
        </h1>
      </header>

      <FilterControls
        ticker={ticker}
        source={source}
        since={since}
        until={until}
        setParam={setParam}
      />

      <ViewToggleBar
        viewMode={viewMode}
        setViewMode={setViewMode}
        selected={selected}
        onCompare={handleCompare}
      />

      <SnapshotsContent
        isLoading={isLoading}
        rows={rows}
        viewMode={viewMode}
        ticker={ticker}
        selected={selected}
        onToggle={handleToggle}
      />

      {drawerOpen && selected.length === 2 && (
        <CompareOverlay selected={selected} onClose={() => setDrawerOpen(false)} />
      )}
    </main>
  );
}
