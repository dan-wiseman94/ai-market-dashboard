import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchFirings, type Firing } from "@/api/triggers";

function describeValues(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(2) : v}`)
    .join(", ");
}

function RefLink({ id, to }: { id: number | null; to: string }) {
  if (id === null) return <span className="text-neutral-600">—</span>;
  return (
    <Link to={`${to}/${id}`} className="text-indigo-700 dark:text-indigo-400">
      #{id}
    </Link>
  );
}

function StatusBadge({ firing }: { firing: Firing }) {
  if (firing.cost_capped) {
    return <span className="text-amber-700 dark:text-amber-400 text-xs">cost-capped</span>;
  }
  if (firing.thread_id) {
    return <span className="text-emerald-700 dark:text-emerald-400 text-xs">fired</span>;
  }
  return <span className="text-rose-700 dark:text-rose-400 text-xs">error</span>;
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
              <RefLink id={f.snapshot_id} to="/snapshots" />
            </td>
            <td className="py-2">
              <RefLink id={f.thread_id} to="/threads" />
            </td>
            <td className="py-2">
              <StatusBadge firing={f} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
