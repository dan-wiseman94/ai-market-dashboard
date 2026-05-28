import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRecentFirings, type Firing } from "@/api/triggers";

const TIME_FMT = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" });
const DATE_FMT = new Intl.DateTimeFormat([], { month: "short", day: "numeric" });

function describeMatched(values: Firing["matched_values"]): string {
  return Object.entries(values)
    .filter(([k, v]) => v !== null && !k.startsWith("_prior:"))
    .map(([k, v]) => {
      if (k.startsWith("price:")) return `${k.slice("price:".length)} ${Number(v).toFixed(2)}`;
      if (k.startsWith("pct_change:")) {
        const [, ticker, window] = k.split(":");
        const pct = (Number(v) * 100).toFixed(2);
        return `${ticker} ${Number(v) >= 0 ? "+" : ""}${pct}% /${window}`;
      }
      if (k.startsWith("volume_z:")) {
        const [, ticker, window] = k.split(":");
        return `${ticker} vol z${Number(v).toFixed(2)} /${window}`;
      }
      if (k === "vix") return `VIX ${Number(v).toFixed(2)}`;
      return `${k} ${v}`;
    })
    .join(" · ");
}

function FiringStatus({ firing }: { firing: Firing }) {
  if (firing.cost_capped) {
    return <span className="ledger-pill" data-tone="copper">cost-capped</span>;
  }
  if (firing.thread_id) {
    return (
      <Link
        to={`/threads/${firing.thread_id}`}
        className="ledger-pill hover:border-copper-500/60 hover:text-copper-200 transition-colors"
      >
        open thread →
      </Link>
    );
  }
  return null;
}

function FiringRow({ firing }: { firing: Firing }) {
  const firedAt = new Date(firing.fired_at);
  const matched = describeMatched(firing.matched_values);
  return (
    <li className="group relative hover:bg-copper-500/[0.04] transition-colors">
      <div className="flex items-center gap-4 px-5 py-3">
        <div className="flex flex-col min-w-[96px]">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
            {TIME_FMT.format(firedAt)}
          </span>
          <span className="font-mono text-[10px] text-ink-600 mt-0.5">
            {DATE_FMT.format(firedAt)}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-display text-[15px] text-ink-100 truncate">
            {firing.trigger_name}
          </div>
          <div className="text-[12px] text-ink-400 font-mono mt-0.5 truncate">
            {matched || <span className="italic">condition met</span>}
          </div>
        </div>
        <div className="shrink-0">
          <FiringStatus firing={firing} />
        </div>
      </div>
    </li>
  );
}

export default function RecentTriggersCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["recent-firings"],
    queryFn: () => fetchRecentFirings(5),
    refetchInterval: 30_000,
  });

  if (isLoading || !data?.length) return null;

  return (
    <div className="ledger-surface overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Latest firings</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/triggers"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          All triggers →
        </Link>
      </div>
      <ul className="divide-y divide-rule-soft">
        {data.map((f: Firing) => (
          <FiringRow key={f.id} firing={f} />
        ))}
      </ul>
    </div>
  );
}
