import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useRecall, useRecallBackfill, useRecallStatus } from "@/hooks/useRecall";
import { Skeleton, SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import type { RecallHit } from "@/api/recall";

const KIND_OPTIONS = [
  { value: "", label: "All kinds" },
  { value: "message", label: "Messages" },
  { value: "snapshot", label: "Snapshots" },
  { value: "thesis", label: "Theses" },
  { value: "journal", label: "Journal" },
  { value: "observation", label: "Observations" },
  { value: "postmortem", label: "Post-mortems" },
];

function KindBadge({ kind }: { kind: string }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-rule text-ink-400">
      {kind}
    </span>
  );
}

function ModeBadge({
  mode,
  testId = "mode-badge",
}: {
  mode: "semantic" | "keyword";
  testId?: string;
}) {
  return (
    <span
      data-testid={testId}
      className={[
        "font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border",
        mode === "semantic"
          ? "border-copper-600 text-copper-300"
          : "border-rule text-ink-400",
      ].join(" ")}
    >
      {mode}
    </span>
  );
}

function IndexCounts({ queuedAt }: { queuedAt: number | null }) {
  const { data, isLoading, isError } = useRecallStatus(queuedAt);

  if (isLoading) {
    return <Skeleton className="h-5 w-64" where="recall-status" />;
  }
  // Degrade gracefully: the readout is a nicety — never block search on it.
  if (isError || !data) return null;

  const { total = 0, ...byKind } = data.counts;
  return (
    <div
      data-testid="recall-status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1"
    >
      <ModeBadge mode={data.mode} testId="recall-status-mode" />
      <span className="font-mono text-[11px] text-ink-400">
        {total} indexed
      </span>
      {Object.entries(byKind).map(([kind, count]) => (
        <span key={kind} className="font-mono text-[10px] text-ink-500">
          <span className="capitalize">{kind}</span>{" "}
          <span className="text-ink-400">{count}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * Index health plus the backfill control.
 *
 * POST /api/recall/backfill/ is fire-and-forget — a 202 with a task id and no
 * completion event — so this says "queued", never "done", and re-reads the
 * counts above on a short poll so progress is actually visible.
 */
function IndexHealth() {
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const backfill = useRecallBackfill();
  const { push } = useToast();
  const helpId = useId();

  function run() {
    backfill.mutate(undefined, {
      onSuccess: (data) => {
        setTaskId(data.task_id);
        setQueuedAt(Date.now());
        push({ kind: "info", text: "Backfill queued." });
      },
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });
  }

  return (
    <fieldset className="rounded border border-rule p-3">
      <legend className="px-1 text-[10px] uppercase tracking-wider text-ink-500">
        Index health
      </legend>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <IndexCounts queuedAt={queuedAt} />
        <button
          type="button"
          onClick={run}
          disabled={backfill.isPending}
          aria-describedby={helpId}
          className="rounded border border-copper-600 px-3 py-1 text-[12px] text-copper-200 transition-colors hover:bg-copper-900/30 disabled:opacity-50"
        >
          {backfill.isPending ? "Queuing…" : "Backfill index"}
        </button>
      </div>
      <p id={helpId} className="mt-2 text-[11px] leading-relaxed text-ink-500">
        Re-embeds every document still pending semantic indexing — messages, snapshots, theses,
        journal entries, observations and post-mortems written before the index existed, or while
        it was unavailable. Embeddings are computed locally, so this costs worker CPU and no
        provider spend. Idempotent: pressing it again only picks up what is still missing.
      </p>
      {taskId && (
        <p
          data-testid="recall-backfill-queued"
          role="status"
          className="mt-2 text-[11px] text-ink-400"
        >
          Queued as task <span className="font-mono">{taskId}</span>. Queued is not finished —
          the worker reports no completion event, so the counts above re-read every 5s for the
          next couple of minutes.
        </p>
      )}
    </fieldset>
  );
}

function HitRow({ hit }: { hit: RecallHit }) {
  return (
    <div className="flex flex-col gap-1 py-3 border-b border-rule-soft last:border-0">
      <div className="flex items-center gap-2">
        <KindBadge kind={hit.kind} />
        {hit.tickers.length > 0 && (
          <span className="font-mono text-[10px] text-ink-500">
            {hit.tickers.join(" · ")}
          </span>
        )}
        {hit.source_created_at && (
          <span className="font-mono text-[10px] text-ink-600 ml-auto">
            {new Date(hit.source_created_at).toLocaleDateString()}
          </span>
        )}
      </div>
      <p className="text-[13px] text-ink-300 leading-relaxed line-clamp-3">{hit.snippet}</p>
      <Link
        to={hit.link}
        className="font-mono text-[11px] text-copper-400 hover:text-copper-200 transition-colors"
      >
        → {hit.link}
      </Link>
    </div>
  );
}

export default function RecallPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [kind, setKind] = useState("");
  const [ticker, setTicker] = useState("");

  // Derive from state — no setState in effect
  const { data, isLoading } = useRecall(submitted, { kind: kind || undefined, ticker: ticker || undefined });

  const results = data?.results ?? [];
  const mode = data?.mode;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(query.trim());
  }

  const grouped: Record<string, RecallHit[]> = {};
  for (const hit of results) {
    (grouped[hit.kind] ??= []).push(hit);
  }

  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <header className="mb-6 pb-6 border-b border-rule">
        <span className="ledger-eyebrow">Recall</span>
        <h1
          className="ledger-display"
          style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}
        >
          Semantic Recall
        </h1>
      </header>

      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex flex-wrap gap-3 items-end">
          <label className="flex flex-col gap-1 text-xs text-ink-400 flex-1 min-w-64">
            Query
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. NVDA bullish into earnings…"
              data-testid="recall-query-input"
              className="px-3 py-2 rounded border border-rule bg-ink-900 text-ink-100 text-sm focus:border-copper-500 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-ink-400">
            Kind
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="px-2 py-2 rounded border border-rule bg-ink-900 text-ink-100 text-sm w-36 focus:border-copper-500 focus:outline-none"
            >
              {KIND_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-ink-400">
            Ticker
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="NVDA"
              className="px-2 py-2 rounded border border-rule bg-ink-900 text-ink-100 text-sm w-24 focus:border-copper-500 focus:outline-none"
            />
          </label>

          <button
            type="submit"
            className="px-4 py-2 rounded border border-copper-600 text-copper-200 hover:bg-copper-900/30 transition-colors text-sm font-medium"
          >
            Search
          </button>
        </div>
      </form>

      {/* Outside the search form on purpose: the backfill is its own action, not
          a second submit path for the query. */}
      <div className="mb-6">
        <IndexHealth />
      </div>

      {submitted && (
        <div className="flex items-center gap-3 mb-4">
          {mode && <ModeBadge mode={mode} />}
          <span className="text-[12px] text-ink-500 font-mono">
            {results.length} result{results.length !== 1 ? "s" : ""} for "{submitted}"
          </span>
        </div>
      )}

      {isLoading ? (
        <SkeletonRows rows={5} />
      ) : submitted && results.length === 0 ? (
        <EmptyState
          title="No results found"
          body="Try a different query, or wait for the index to populate."
        />
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([groupKind, hits]) => (
            <section key={groupKind}>
              <div className="ledger-eyebrow mb-3 flex items-center gap-2">
                <span className="capitalize">{groupKind}</span>
                <span className="flex-1 h-px bg-rule" />
                <span className="font-mono text-[10px] text-ink-500">{hits.length}</span>
              </div>
              <div className="ledger-surface rounded-sm px-4">
                {hits.map((hit) => (
                  <HitRow key={`${hit.kind}-${hit.object_id}`} hit={hit} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
