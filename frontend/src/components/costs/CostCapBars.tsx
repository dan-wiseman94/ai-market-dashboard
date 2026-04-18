import type { CapRow } from "@/api/costs";

function barFillClass(pct: number): string {
  // Legacy-compat bg-* classes kept alongside our token vars so older snapshot
  // tests and existing Tailwind JIT output remain happy.
  if (pct >= 1.0) return "bg-rose-500";
  if (pct >= 0.8) return "bg-amber-500";
  return "bg-emerald-500";
}

function barGradient(pct: number): string {
  if (pct >= 1.0)
    return "linear-gradient(90deg, var(--loss-500) 0%, var(--loss-400) 100%)";
  if (pct >= 0.8)
    return "linear-gradient(90deg, var(--copper-500) 0%, var(--copper-300) 100%)";
  return "linear-gradient(90deg, var(--gain-500) 0%, var(--gain-400) 100%)";
}

function toneClass(pct: number): string {
  if (pct >= 1.0) return "text-loss";
  if (pct >= 0.8) return "text-copper-300";
  return "text-gain";
}

function Bar({
  label, cap, spent, pct,
}: { label: string; cap: string; spent: string; pct: number }) {
  return (
    <div className="grid grid-cols-[72px_1fr_auto_48px] items-center gap-4 text-[12px]">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-400">{label}</span>
      <div className="relative h-[6px] bg-ink-void rounded-sm overflow-hidden border border-rule">
        <div
          className={`${barFillClass(pct)} h-full transition-[width] duration-700 ease-ledger`}
          style={{ width: `${Math.min(100, pct * 100)}%`, background: barGradient(pct) }}
        />
      </div>
      <span className="font-mono tabular-nums text-ink-200">
        {`$${spent} / $${cap}`}
      </span>
      <span className={`font-mono tabular-nums text-right ${toneClass(pct)}`}>
        {`${Math.round(pct * 100)}%`}
      </span>
    </div>
  );
}

export default function CostCapBars({ rows }: { rows: CapRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="ledger-surface overflow-hidden">
      <div className="px-5 py-3 border-b border-rule flex items-center gap-3">
        <span className="ledger-eyebrow">Caps</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <span className="font-mono text-[10px] text-ink-500">{rows.length} provider{rows.length === 1 ? "" : "s"}</span>
      </div>
      <div className="divide-y divide-rule-soft">
        {rows.map((r) => (
          <div key={r.provider} className="px-5 py-3 space-y-2">
            <div className="flex items-baseline gap-3">
              <span className="font-display text-[13px] text-ink-100 uppercase tracking-wider">{r.provider}</span>
              <span className="flex-1 h-px bg-rule-soft" />
            </div>
            <Bar label="Daily" cap={r.daily.cap} spent={r.daily.spent} pct={r.daily.pct} />
            {r.monthly && <Bar label="Monthly" cap={r.monthly.cap} spent={r.monthly.spent} pct={r.monthly.pct} />}
          </div>
        ))}
      </div>
    </div>
  );
}
