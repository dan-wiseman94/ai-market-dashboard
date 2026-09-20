import { useRef } from "react";
import { SaveCardButton } from "./SaveCardButton";
import AiAttribution from "@/components/ai/AiAttribution";
import { providerLabel } from "@/api/ai";
import { BIAS_COLOR } from "@/components/ObservationReportCard";
import type { Bias, ConsensusReport } from "@/api/observation";

function BiasPill({ bias }: { bias: Bias | null }) {
  if (!bias) return <span className="text-ink-500">—</span>;
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${BIAS_COLOR[bias]}`}
    >
      {bias}
    </span>
  );
}

/** "2 of 3 agree (67%)" — null below two takes, where no consensus is meaningful. */
export function agreementLine(r: ConsensusReport): string | null {
  if (r.n_providers < 2 || r.bias_agreement == null) return null;
  const agreeing = Math.round(r.bias_agreement * r.n_providers);
  return `${agreeing} of ${r.n_providers} agree (${Math.round(r.bias_agreement * 100)}%)`;
}

/** Cross-provider agreement on one snapshot: the headline signal, each provider's
 * take, and where they split per ticker. Degrades honestly to the single-provider
 * note rather than implying a consensus that was never reached. */
export default function ConsensusReportCard({ report }: { report: ConsensusReport }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const line = agreementLine(report);
  const columns = report.takes.map((t) => `${t.provider}/${t.model}`);

  return (
    <div ref={cardRef} className="space-y-3">
      <div className="flex flex-wrap items-start gap-3">
        <BiasPill bias={report.modal_bias} />
        <h3 className="flex-1 font-medium text-ink-100">{line ?? report.note ?? "Consensus"}</h3>
        {report.divergent && (
          <span className="ledger-pill" data-tone="copper">Divergent — do more homework</span>
        )}
        <SaveCardButton targetRef={cardRef} filename="consensus.png" />
      </div>

      {line && report.note && <p className="text-[12px] text-ink-400">{report.note}</p>}

      <section>
        <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-copper-400">
          Takes
        </div>
        <ul className="space-y-1">
          {report.takes.map((t) => (
            <li key={`${t.provider}/${t.model}`} className="flex items-center gap-2 text-xs">
              <AiAttribution provider={t.provider} model={t.model} />
              <BiasPill bias={t.bias} />
            </li>
          ))}
        </ul>
      </section>

      {Object.keys(report.per_ticker).length > 0 && (
        <section className="min-w-0 overflow-x-auto">
          <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-copper-400">
            Per ticker
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-400">
                <th className="py-1 pr-3 font-normal">Ticker</th>
                {columns.map((c) => (
                  <th key={c} className="py-1 pr-3 font-normal">
                    {providerLabel(c.split("/")[0])}
                  </th>
                ))}
                <th className="py-1 text-right font-normal">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.per_ticker).map(([ticker, row]) => (
                <tr key={ticker} aria-label={ticker} className="border-t border-rule-soft">
                  <td className="py-1 pr-3 font-mono text-ink-100">{ticker}</td>
                  {columns.map((c) => (
                    <td key={c} className="py-1 pr-3"><BiasPill bias={row.takes[c] ?? null} /></td>
                  ))}
                  <td className="py-1 text-right tabular-nums text-ink-300">
                    {row.agreement == null ? "—" : `${Math.round(row.agreement * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
