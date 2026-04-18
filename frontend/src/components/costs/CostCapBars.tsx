import type { CapRow } from "@/api/costs";

function barColor(pct: number): string {
  if (pct >= 1.0) return "bg-rose-500";
  if (pct >= 0.8) return "bg-amber-500";
  return "bg-emerald-500";
}

function Bar({ label, cap, spent, pct }: { label: string; cap: string; spent: string; pct: number }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-16 text-slate-500">{label}</span>
      <div className="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
        <div className={`${barColor(pct)} h-full`} style={{ width: `${Math.min(100, pct * 100)}%` }} />
      </div>
      <span className="font-mono tabular-nums text-slate-300">${spent} / ${cap}</span>
      <span className="w-10 text-right text-slate-400">{Math.round(pct * 100)}%</span>
    </div>
  );
}

export default function CostCapBars({ rows }: { rows: CapRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-3 p-3 border border-slate-800 rounded">
      {rows.map((r) => (
        <div key={r.provider} className="space-y-1.5">
          <div className="text-xs uppercase text-slate-500">{r.provider}</div>
          <Bar label="Daily" cap={r.daily.cap} spent={r.daily.spent} pct={r.daily.pct} />
          {r.monthly && <Bar label="Monthly" cap={r.monthly.cap} spent={r.monthly.spent} pct={r.monthly.pct} />}
        </div>
      ))}
    </div>
  );
}
