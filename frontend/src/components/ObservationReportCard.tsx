type Bias = "bullish" | "bearish" | "neutral" | "mixed";

export type ObservationReport = {
  headline: string;
  bias: Bias;
  summary: string;
  signals: Array<{
    ticker: string;
    bias: Bias;
    thesis: string;
    invalidation: string;
    confidence: number;
  }>;
  key_levels: Array<{
    label: string;
    price: number;
    kind: "support" | "resistance" | "pivot" | "target";
  }>;
  risks: string[];
  next_check_in: string;
};

const BIAS_COLOR: Record<Bias, string> = {
  bullish: "text-emerald-700 dark:text-emerald-400 border-emerald-500/40",
  bearish: "text-rose-700 dark:text-rose-400 border-rose-500/40",
  neutral: "text-slate-300 border-slate-500/40",
  mixed: "text-amber-700 dark:text-amber-400 border-amber-500/40",
};

function SectionHeading({ children }: { children: string }) {
  return (
    <div className="font-mono text-[10px] uppercase tracking-wider text-copper-400 mb-1">
      {children}
    </div>
  );
}

export default function ObservationReportCard({ report }: { report: ObservationReport }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3">
        <span className={`shrink-0 inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider border rounded ${BIAS_COLOR[report.bias]}`}>
          {report.bias}
        </span>
        <h3 className="font-medium text-ink-100">{report.headline}</h3>
      </div>
      <p className="text-sm text-ink-300">{report.summary}</p>

      {report.signals.length > 0 && (
        <section>
          <SectionHeading>Signals</SectionHeading>
          <ul className="space-y-1">
            {report.signals.map((s, i) => (
              <li key={i} className="text-xs text-ink-200">
                <span className="font-mono">{s.ticker}</span>
                <span className={`ml-2 ${BIAS_COLOR[s.bias].split(" ")[0]}`}>{s.bias}</span>
                <span className="ml-2 text-slate-400">({(s.confidence * 100).toFixed(0)}%)</span>
                <div className="text-slate-300">{s.thesis}</div>
                <div className="text-slate-500 text-[11px]">Invalidates: {s.invalidation}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.key_levels.length > 0 && (
        <section>
          <SectionHeading>Key levels</SectionHeading>
          <ul className="text-xs text-ink-200 grid grid-cols-2 gap-x-4 gap-y-0.5">
            {report.key_levels.map((k, i) => (
              <li key={i}>
                <span className="font-mono">${k.price.toFixed(2)}</span>
                <span className="ml-2 text-slate-400">{k.kind}</span>
                <span className="ml-2 text-slate-300">— {k.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.risks.length > 0 && (
        <section>
          <SectionHeading>Risks</SectionHeading>
          <ul className="text-xs text-ink-300 list-disc pl-5">
            {report.risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </section>
      )}

      <div className="text-[11px] text-slate-500 italic">Next check: {report.next_check_in}</div>
    </div>
  );
}
