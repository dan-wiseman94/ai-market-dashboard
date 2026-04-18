import { Link } from "react-router-dom";
import type { CostsSummary } from "@/api/costs";
import { usd } from "@/utils/format";

function Dollar({ v, dim = false }: { v: string; dim?: boolean }) {
  return (
    <span className={`font-mono tabular-nums ${dim ? "text-ink-400" : "text-ink-100"}`}>
      {usd(v)}
    </span>
  );
}

function Th({ children, right = false }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={[
        "font-mono text-[10px] uppercase tracking-loose2 text-ink-400 font-normal px-4 py-2.5",
        right ? "text-right" : "text-left",
      ].join(" ")}
    >
      {children}
    </th>
  );
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
      <span className="ledger-eyebrow">{title}</span>
      <span className="flex-1 h-px bg-rule-soft" />
      {count !== undefined && (
        <span className="font-mono text-[10px] text-ink-500 tabular-nums">{count} row{count === 1 ? "" : "s"}</span>
      )}
    </div>
  );
}

export default function BreakdownTables({ summary }: { summary: CostsSummary }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <section className="ledger-surface overflow-hidden">
        <SectionHeader title="By provider" count={summary.by_provider.length} />
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-rule-soft">
              <Th>Provider</Th>
              <Th right>Runs</Th>
              <Th right>In</Th>
              <Th right>Out</Th>
              <Th right>Cost</Th>
            </tr>
          </thead>
          <tbody>
            {summary.by_provider.map((r, i) => (
              <tr key={r.provider} className={i > 0 ? "border-t border-rule-soft" : ""}>
                <td className="px-4 py-2.5 capitalize font-display text-[13px] text-ink-100">{r.provider}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-ink-300">{r.runs}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-ink-400">{r.input_tokens.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-ink-400">{r.output_tokens.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-right"><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="ledger-surface overflow-hidden">
        <SectionHeader title="By model" count={summary.by_model.length} />
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-rule-soft">
              <Th>Provider</Th>
              <Th>Model</Th>
              <Th right>Runs</Th>
              <Th right>Cost</Th>
            </tr>
          </thead>
          <tbody>
            {summary.by_model.map((r, i) => (
              <tr key={`${r.provider}/${r.model}`} className={i > 0 ? "border-t border-rule-soft" : ""}>
                <td className="px-4 py-2.5 capitalize font-mono text-[11px] text-ink-400">{r.provider}</td>
                <td className="px-4 py-2.5 font-mono text-[12px] text-ink-100">{r.model}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-ink-300">{r.runs}</td>
                <td className="px-4 py-2.5 text-right"><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="lg:col-span-2 ledger-surface overflow-hidden">
        <SectionHeader title="Top 10 threads by cost" count={summary.by_thread.length} />
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-rule-soft">
              <Th>Thread</Th>
              <Th right>Runs</Th>
              <Th right>Cost</Th>
            </tr>
          </thead>
          <tbody>
            {summary.by_thread.map((r, i) => (
              <tr
                key={r.thread_id}
                className={[
                  "group transition-colors hover:bg-copper-500/[0.04]",
                  i > 0 ? "border-t border-rule-soft" : "",
                ].join(" ")}
              >
                <td className="px-4 py-2.5">
                  <Link
                    to={`/threads/${r.thread_id}`}
                    className="font-display text-[14px] text-ink-100 hover:text-copper-200 transition-colors"
                  >
                    {r.title || <span className="italic text-ink-400">Thread {r.thread_id}</span>}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums text-ink-300">{r.runs}</td>
                <td className="px-4 py-2.5 text-right"><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
