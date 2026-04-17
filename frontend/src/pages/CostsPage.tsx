import { useCostsToday } from "@/hooks/useCosts";

export default function CostsPage() {
  const { data, isLoading } = useCostsToday();
  if (isLoading) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Costs — today</h1>
      <div className="text-3xl tabular-nums">
        ${Number(data?.total_usd ?? "0").toFixed(4)}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-400 text-left">
            <th className="py-2">Provider</th>
            <th className="py-2">Runs</th>
            <th className="py-2">Input tok</th>
            <th className="py-2">Cached</th>
            <th className="py-2">Output tok</th>
            <th className="py-2">Cost</th>
          </tr>
        </thead>
        <tbody>
          {(data?.by_provider ?? []).map((p) => (
            <tr key={p.provider} className="border-t border-slate-800">
              <td className="py-2 capitalize font-medium">{p.provider}</td>
              <td className="py-2 tabular-nums">{p.runs}</td>
              <td className="py-2 tabular-nums">{p.input_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums text-slate-500">{p.cached_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums">{p.output_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums">${Number(p.cost_usd).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
