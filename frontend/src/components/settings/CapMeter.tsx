function barGradient(pct: number): string {
  if (pct >= 1.0) return "linear-gradient(90deg, var(--loss-500) 0%, var(--loss-400) 100%)";
  if (pct >= 0.8) return "linear-gradient(90deg, var(--copper-500) 0%, var(--copper-300) 100%)";
  return "linear-gradient(90deg, var(--gain-500) 0%, var(--gain-400) 100%)";
}
function toneClass(pct: number): string {
  if (pct >= 1.0) return "text-loss";
  if (pct >= 0.8) return "text-copper-300";
  return "text-gain";
}

type Props = { label: string; cap: string; spent: string; pct: number };

export default function CapMeter({ label, cap, spent, pct }: Props) {
  return (
    <div className="grid grid-cols-[64px_1fr_auto_44px] items-center gap-3 text-[12px]">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-400">{label}</span>
      <div className="relative h-[6px] bg-ink-void rounded-sm overflow-hidden border border-rule">
        <div
          data-testid="capmeter-fill"
          className="h-full transition-[width] duration-700 ease-ledger"
          style={{ width: `${Math.min(100, pct * 100)}%`, background: barGradient(pct) }}
        />
      </div>
      <span className="font-mono tabular-nums text-ink-200">{`$${spent} / $${cap}`}</span>
      <span className={`font-mono tabular-nums text-right ${toneClass(pct)}`}>{`${Math.round(pct * 100)}%`}</span>
    </div>
  );
}
