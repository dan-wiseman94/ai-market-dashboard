import { useParams } from "react-router-dom";
import { useCostsSnapshot } from "@/hooks/useCosts";

export default function SnapshotCostPage() {
  const { id } = useParams();
  const snapId = id ? Number(id) : null;
  const { data, isLoading } = useCostsSnapshot(snapId);

  if (isLoading) return <main className="p-6">Loading…</main>;
  if (!data || data.length === 0) return <main className="p-6 text-slate-500">No data for snapshot {id}.</main>;

  return (
    <main className="p-6 max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-semibold">Snapshot {id} — cost attribution</h1>
      <table className="w-full text-sm border border-slate-800 rounded">
        <thead className="bg-slate-900">
          <tr className="text-slate-400 text-left">
            <th className="py-1.5 px-2">Section</th>
            <th className="py-1.5 px-2">Tokens</th>
            <th className="py-1.5 px-2">Cost share</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.section} className="border-t border-slate-800">
              <td className="py-1.5 px-2">{r.section}</td>
              <td className="py-1.5 px-2 tabular-nums">{r.payload_tokens.toLocaleString()}</td>
              <td className="py-1.5 px-2 font-mono">${Number(r.cost_share_usd).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-500">Attribution is proportional to the section's share of payload tokens.</p>
    </main>
  );
}
