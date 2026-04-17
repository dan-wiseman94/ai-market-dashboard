import { useMarketContext } from "@/hooks/useMarketContext";

function Chip({ label, value, tone = "text-slate-200" }: { label: string; value: number | null; tone?: string }) {
  return (
    <div className="px-3 py-1.5 rounded border border-slate-800 bg-slate-900/50 min-w-[90px]">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-sm tabular-nums ${tone}`}>{value?.toFixed(2) ?? "—"}</div>
    </div>
  );
}

export default function MarketContextStrip() {
  const { data } = useMarketContext();
  if (!data) return null;
  return (
    <div className="flex flex-wrap gap-2">
      <Chip label="SPY" value={data.spy_last} />
      <Chip label="QQQ" value={data.qqq_last} />
      <Chip label="VIX" value={data.vix_last} tone="text-amber-400" />
      {Object.entries(data.sectors).map(([k, v]) => (
        <Chip key={k} label={k} value={v} />
      ))}
    </div>
  );
}
