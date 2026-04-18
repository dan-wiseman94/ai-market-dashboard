import { Link } from "react-router-dom";
import type { CostsSummary } from "@/api/costs";

function Dollar({ v }: { v: string }) {
  return <span className="font-mono tabular-nums">${Number(v).toFixed(4)}</span>;
}

export default function BreakdownTables({ summary }: { summary: CostsSummary }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <section className="border border-slate-800 rounded p-3">
        <h2 className="text-sm uppercase text-slate-500 mb-2">By provider</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1">Provider</th><th>Runs</th><th>In</th><th>Out</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {summary.by_provider.map((r) => (
              <tr key={r.provider} className="border-t border-slate-800">
                <td className="py-1 capitalize">{r.provider}</td>
                <td>{r.runs}</td>
                <td className="tabular-nums">{r.input_tokens.toLocaleString()}</td>
                <td className="tabular-nums">{r.output_tokens.toLocaleString()}</td>
                <td><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="border border-slate-800 rounded p-3">
        <h2 className="text-sm uppercase text-slate-500 mb-2">By model</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1">Provider</th><th>Model</th><th>Runs</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {summary.by_model.map((r) => (
              <tr key={`${r.provider}/${r.model}`} className="border-t border-slate-800">
                <td className="py-1 capitalize">{r.provider}</td>
                <td className="text-slate-300">{r.model}</td>
                <td>{r.runs}</td>
                <td><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="md:col-span-2 border border-slate-800 rounded p-3">
        <h2 className="text-sm uppercase text-slate-500 mb-2">Top 10 threads by cost</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1">Thread</th><th>Runs</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {summary.by_thread.map((r) => (
              <tr key={r.thread_id} className="border-t border-slate-800">
                <td className="py-1">
                  <Link to={`/threads/${r.thread_id}`} className="text-emerald-300 hover:underline">
                    {r.title || `Thread ${r.thread_id}`}
                  </Link>
                </td>
                <td>{r.runs}</td>
                <td><Dollar v={r.cost_usd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
