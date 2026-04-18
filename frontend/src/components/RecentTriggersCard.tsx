import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRecentFirings, type Firing } from "@/api/triggers";

function describeMatched(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => {
      if (k.startsWith("price:")) return `${k.slice("price:".length)}=${Number(v).toFixed(2)}`;
      if (k.startsWith("pct_change:")) {
        const [, ticker, window] = k.split(":");
        const pct = (Number(v) * 100).toFixed(2);
        return `${ticker} ${Number(v) >= 0 ? "+" : ""}${pct}% /${window}`;
      }
      if (k === "vix") return `vix=${Number(v).toFixed(2)}`;
      return `${k}=${v}`;
    })
    .join(", ");
}

export default function RecentTriggersCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["recent-firings"],
    queryFn: () => fetchRecentFirings(5),
    refetchInterval: 30_000,
  });

  if (isLoading || !data?.length) return null;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold">Recent triggers</h3>
        <Link to="/triggers" className="text-xs text-neutral-400 hover:text-indigo-400">view all →</Link>
      </div>
      <ul className="space-y-1">
        {data.map((f) => (
          <li key={f.id} className="text-sm flex items-baseline gap-2">
            <span className="font-medium">{f.trigger_name}</span>
            <span className="text-neutral-500">·</span>
            <span className="text-neutral-400 tabular-nums">
              {new Date(f.fired_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            <span className="text-neutral-500">·</span>
            <span className="text-neutral-300">{describeMatched(f.matched_values)}</span>
            {f.cost_capped ? (
              <span className="ml-auto text-xs text-amber-400">cost-capped</span>
            ) : f.thread_id ? (
              <Link to={`/threads/${f.thread_id}`} className="ml-auto text-xs text-indigo-400">thread →</Link>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
