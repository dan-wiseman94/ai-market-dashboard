import { useLatestBriefing, useRunBriefing } from "@/hooks/useBriefing";
import type { Briefing, BriefingData, BriefingThesis } from "@/api/briefing";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

function RunButton({
  className,
  isPending,
  onRun,
}: {
  className: string;
  isPending: boolean;
  onRun: () => void;
}) {
  return (
    <button className={className} disabled={isPending} onClick={onRun}>
      {isPending ? "Running…" : "Run now"}
    </button>
  );
}

function BriefingHeader({ briefing, isPending, onRun }: { briefing: Briefing; isPending: boolean; onRun: () => void }) {
  return (
    <header className="pb-6 border-b border-rule">
      <div className="flex items-center justify-between">
        <div>
          <span className="ledger-eyebrow">Briefing</span>
          <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
            Morning briefing
          </h1>
        </div>
        <RunButton
          className="rounded border border-rule px-3 py-1 text-sm text-ink-400 hover:text-copper-300 disabled:opacity-50 transition-colors"
          isPending={isPending}
          onRun={onRun}
        />
      </div>
      {briefing.status === "failed" && (
        <p className="mt-2 text-sm text-rose-700 dark:text-rose-400">Last briefing failed to assemble. Try "Run now".</p>
      )}
    </header>
  );
}

function SynthesisSection({ text }: { text: string }) {
  return (
    <section className="rounded border border-rule p-4">
      <h2 className="mb-2 text-sm font-semibold text-ink-400 uppercase tracking-wide">
        Synthesis
      </h2>
      {text ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
      ) : (
        <p className="text-sm text-muted italic">
          Synthesizing… (refreshes automatically)
        </p>
      )}
    </section>
  );
}

function SectionHeading({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <h2 className="ledger-eyebrow">{title}</h2>
      <span className="flex-1 h-px bg-rule" />
    </div>
  );
}

function fmtPct(v: number | null) {
  return v != null ? `${v}%` : "—";
}

function ThesisRow({ t }: { t: BriefingThesis }) {
  return (
    <tr className="border-b border-rule">
      <td className="py-2 font-mono text-copper-400 uppercase">{t.ticker}</td>
      <td className="py-2 text-ink-300">{t.direction}</td>
      <td className="py-2 text-right text-ink-300">
        {t.current != null ? t.current : "—"}
      </td>
      <td className="py-2 text-right text-ink-300">{fmtPct(t.pct_to_target)}</td>
      <td className="py-2 text-right text-ink-300">{fmtPct(t.pct_to_invalidation)}</td>
      <td className="py-2 text-right text-ink-400">{t.conviction}</td>
    </tr>
  );
}

function ThesesSection({ theses }: { theses: BriefingThesis[] }) {
  return (
    <section>
      <SectionHeading title="Open theses" />
      {theses.length === 0 ? (
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
            {theses.map((t) => (
              <ThesisRow key={t.id} t={t} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function EventRow({ ev }: { ev: { title?: string; ticker?: string; days_until?: number } }) {
  const label = ev.title ?? (ev.ticker ? `${ev.ticker} earnings` : "Event");
  return (
    <li className="flex items-baseline justify-between border-b border-rule py-2">
      <span className="text-ink-200">{label}</span>
      {ev.days_until != null && (
        <span className="text-sm text-muted">in {ev.days_until}d</span>
      )}
    </li>
  );
}

function EventsSection({ events }: { events: BriefingData["events"] }) {
  return (
    <section>
      <SectionHeading title="Upcoming events" />
      {events.earnings.length + events.macro.length === 0 ? (
        <EmptyState title="No upcoming events" />
      ) : (
        <ul className="text-sm space-y-1">
          {[...events.earnings, ...events.macro].map((e, i) => (
            <EventRow
              key={i}
              ev={e as { title?: string; ticker?: string; days_until?: number }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function TriggersSection({ triggers }: { triggers: BriefingData["triggers"] }) {
  return (
    <section>
      <SectionHeading title="Overnight triggers" />
      {triggers.length === 0 ? (
        <EmptyState title="No triggers fired" />
      ) : (
        <ul className="text-sm space-y-1">
          {triggers.map((t) => (
            <li key={t.fired_at} className="flex items-baseline justify-between border-b border-rule py-2">
              <span className="font-medium text-ink-200">{t.name}</span>
              <span className="text-muted">{t.summary}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NewsSection({ news }: { news: BriefingData["news"] }) {
  return (
    <section>
      <SectionHeading title="Overnight news" />
      {news.length === 0 ? (
        <EmptyState title="No news" />
      ) : (
        <ul className="text-sm space-y-1">
          {news.map((n, i) => (
            <li key={i} className="flex items-baseline justify-between border-b border-rule py-2">
              <span className="text-ink-200 flex-1 mr-4">{n.headline}</span>
              <span className="text-muted shrink-0">{n.source}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function MarketSection({ market }: { market: Record<string, unknown> }) {
  return (
    <section>
      <SectionHeading title="Market context" />
      {Object.keys(market).length === 0 ? <EmptyState title="No market data" /> : (
        <p className="text-sm">
          SPX {String(market.spx_last ?? "—")} · QQQ{" "}
          {String(market.qqq_last ?? "—")} · VIX{" "}
          {String(market.vix_last ?? "—")}
        </p>
      )}
    </section>
  );
}

export default function BriefingPage() {
  const { data: briefing, isLoading } = useLatestBriefing();
  const run = useRunBriefing();
  const onRun = () => run.mutate();

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
            <RunButton
              className="rounded border border-rule px-3 py-1 text-sm text-ink-400 hover:text-copper-300 disabled:opacity-50"
              isPending={run.isPending}
              onRun={onRun}
            />
          }
        />
      </main>
    );
  }

  const d = briefing.data ?? ({} as Partial<typeof briefing.data>);
  const theses = d.theses ?? [];
  const events = d.events ?? { earnings: [], macro: [] };
  const triggers = d.triggers ?? [];
  const news = d.news ?? [];
  const market = d.market ?? {};

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-8 ledger-fade-in">
      <BriefingHeader briefing={briefing} isPending={run.isPending} onRun={onRun} />
      <SynthesisSection text={briefing.synthesis_text} />
      <ThesesSection theses={theses} />
      <EventsSection events={events} />
      <TriggersSection triggers={triggers} />
      <NewsSection news={news} />
      <MarketSection market={market} />
    </main>
  );
}
