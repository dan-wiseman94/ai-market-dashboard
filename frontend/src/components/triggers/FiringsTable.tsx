import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchFirings, type Firing } from "@/api/triggers";

function describeValues(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(2) : v}`)
    .join(", ");
}

export default function FiringsTable({ triggerId }: { triggerId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["firings", triggerId],
    queryFn: () => fetchFirings(triggerId),
  });

  if (isLoading) return <div className="text-neutral-400">Loading…</div>;
  if (!data?.results?.length) return <div className="text-neutral-500">No firings yet.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="text-neutral-400 text-left">
        <tr>
          <th className="py-2">When</th>
          <th className="py-2">Matched values</th>
          <th className="py-2">Snapshot</th>
          <th className="py-2">Thread</th>
          <th className="py-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {data.results.map((f) => (
          <tr key={f.id} className="border-t border-neutral-800">
            <td className="py-2 tabular-nums text-neutral-400">
              {new Date(f.fired_at).toLocaleString()}
            </td>
            <td className="py-2">{describeValues(f.matched_values)}</td>
            <td className="py-2">
              {f.snapshot_id
                ? <Link to={`/snapshots/${f.snapshot_id}`} className="text-indigo-700 dark:text-indigo-400">#{f.snapshot_id}</Link>
                : <span className="text-neutral-600">—</span>}
            </td>
            <td className="py-2">
              {f.thread_id
                ? <Link to={`/threads/${f.thread_id}`} className="text-indigo-700 dark:text-indigo-400">#{f.thread_id}</Link>
                : <span className="text-neutral-600">—</span>}
            </td>
            <td className="py-2">
              {f.cost_capped
                ? <span className="text-amber-700 dark:text-amber-400 text-xs">cost-capped</span>
                : f.thread_id ? <span className="text-emerald-700 dark:text-emerald-400 text-xs">fired</span>
                : <span className="text-rose-700 dark:text-rose-400 text-xs">error</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
