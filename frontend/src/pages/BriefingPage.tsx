import { useLatestBriefing, useRunBriefing } from "@/hooks/useBriefing";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

export default function BriefingPage() {
  const { data: briefing, isLoading } = useLatestBriefing();
  const run = useRunBriefing();

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!briefing) {
    return (
      <main className="max-w-4xl mx-auto p-6">
        <EmptyState
          title="No briefing yet"
          body="Run your first briefing to see open theses, upcoming events, and overnight activity."
          action={
            <button
              className="rounded border border-rule px-3 py-1 text-sm text-ink-400 hover:text-copper-300 disabled:opacity-50"
              disabled={run.isPending}
              onClick={() => run.mutate()}
            >
              {run.isPending ? "Running…" : "Run now"}
            </button>
          }
        />
      </main>
    );
  }

  const d = briefing.data;

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-8 ledger-fade-in">
      <header className="pb-6 border-b border-rule">
        <div className="flex items-center justify-between">
          <div>
            <span className="ledger-eyebrow">Briefing</span>
            <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
              Morning briefing
            </h1>
          </div>
          <button
            className="rounded border border-rule px-3 py-1 text-sm text-ink-400 hover:text-copper-300 disabled:opacity-50 transition-colors"
            disabled={run.isPending}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "Running…" : "Run now"}
          </button>
        </div>
      </header>

      <section className="rounded border border-rule p-4">
        <h2 className="mb-2 text-sm font-semibold text-ink-400 uppercase tracking-wide">
          Synthesis
        </h2>
        {briefing.synthesis_text ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {briefing.synthesis_text}
          </p>
        ) : (
          <p className="text-sm text-muted italic">
            Synthesizing… (refreshes automatically)
          </p>
        )}
      </section>

      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="ledger-eyebrow">Open theses</h2>
          <span className="flex-1 h-px bg-rule" />
        </div>
        {d.theses.length === 0 ? (
          <EmptyState title="No open theses" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-ink-400 border-b border-rule">
                <th className="text-left pb-2">Ticker</th>
                <th className="text-left pb-2">Dir</th>
                <th className="text-right pb-2">Now</th>
                <th className="text-right pb-2">→Target</th>
                <th className="text-right pb-2">→Invalid.</th>
                <th className="text-right pb-2">Conv</th>
              </tr>
            </thead>
            <tbody>
              {d.theses.map((t) => (
                <tr key={t.id} className="border-b border-rule">
                  <td className="py-2 font-mono text-copper-400 uppercase">
                    {t.ticker}
                  </td>
                  <td className="py-2 text-ink-300">{t.direction}</td>
                  <td className="py-2 text-right text-ink-300">
                    {t.current != null ? t.current : "—"}
                  </td>
                  <td className="py-2 text-right text-ink-300">
                    {t.pct_to_target != null ? `${t.pct_to_target}%` : "—"}
                  </td>
                  <td className="py-2 text-right text-ink-300">
                    {t.pct_to_invalidation != null
                      ? `${t.pct_to_invalidation}%`
                      : "—"}
                  </td>
                  <td className="py-2 text-right text-ink-400">
                    {t.conviction}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="ledger-eyebrow">Upcoming events</h2>
          <span className="flex-1 h-px bg-rule" />
        </div>
        {d.events.earnings.length + d.events.macro.length === 0 ? (
          <EmptyState title="No upcoming events" />
        ) : (
          <ul className="text-sm space-y-1">
            {[...d.events.earnings, ...d.events.macro].map((e, i) => {
              const ev = e as {
                title?: string;
                ticker?: string;
                days_until?: number;
              };
              const label = ev.title ?? (ev.ticker ? `${ev.ticker} earnings` : "Event");
              return (
                <li key={i} className="flex items-baseline justify-between border-b border-rule py-2">
                  <span className="text-ink-200">{label}</span>
                  {ev.days_until != null && (
                    <span className="text-sm text-muted">in {ev.days_until}d</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="ledger-eyebrow">Overnight triggers</h2>
          <span className="flex-1 h-px bg-rule" />
        </div>
        {d.triggers.length === 0 ? (
          <EmptyState title="No triggers fired" />
        ) : (
          <ul className="text-sm space-y-1">
            {d.triggers.map((t) => (
              <li key={t.fired_at} className="flex items-baseline justify-between border-b border-rule py-2">
                <span className="font-medium text-ink-200">{t.name}</span>
                <span className="text-muted">{t.summary}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="ledger-eyebrow">Overnight news</h2>
          <span className="flex-1 h-px bg-rule" />
        </div>
        {d.news.length === 0 ? (
          <EmptyState title="No news" />
        ) : (
          <ul className="text-sm space-y-1">
            {d.news.map((n, i) => (
              <li key={i} className="flex items-baseline justify-between border-b border-rule py-2">
                <span className="text-ink-200 flex-1 mr-4">{n.headline}</span>
                <span className="text-muted shrink-0">{n.source}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
