import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import type { DashboardTriggers, DashboardFiring } from "@/hooks/useDashboard";

const TIME_FMT = new Intl.DateTimeFormat([], {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function FiringRow({ firing }: { firing: DashboardFiring }) {
  return (
    <li className="flex items-center gap-3 px-5 py-2.5 hover:bg-copper-500/[0.04] transition-colors">
      <div className="flex-1 min-w-0">
        <div className="font-display text-[13px] text-ink-100 truncate">
          {firing.trigger_name ?? `Trigger #${firing.trigger_id}`}
        </div>
        <div className="font-mono text-[10px] text-ink-500 mt-0.5">
          {TIME_FMT.format(new Date(firing.fired_at))}
        </div>
      </div>
      {firing.cost_capped && (
        <span className="ledger-pill shrink-0" data-tone="copper">
          capped
        </span>
      )}
    </li>
  );
}

export function ArmedTriggersTile({
  triggers,
}: {
  triggers: DashboardTriggers;
}) {
  return (
    <div className="ledger-surface overflow-hidden h-full">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-rule">
        <span className="ledger-eyebrow">Triggers</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/triggers"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          All →
        </Link>
      </div>
      <div className="px-5 py-3 border-b border-rule-soft flex items-center gap-2">
        <span
          className="font-mono text-[15px] tabular-nums text-copper-300"
          data-testid="triggers-armed-count"
        >
          {triggers.armed_count}
        </span>
        <span className="font-mono text-[11px] text-ink-500">armed</span>
      </div>
      {triggers.latest_firings.length === 0 ? (
        <div className="px-5 py-4">
          <EmptyState title="No recent firings" />
        </div>
      ) : (
        <ul className="divide-y divide-rule-soft">
          {triggers.latest_firings.slice(0, 5).map((f) => (
            <FiringRow key={f.id} firing={f} />
          ))}
        </ul>
      )}
    </div>
  );
}
