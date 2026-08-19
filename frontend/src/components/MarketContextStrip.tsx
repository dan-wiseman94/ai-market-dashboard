import { useMarketContext } from "@/hooks/useMarketContext";

function Headline({
  label, value, tone = "default", hint,
}: {
  label: string;
  value: number | null;
  tone?: "default" | "warn";
  hint?: string;
}) {
  const color = tone === "warn" ? "text-copper-300" : "text-ink-50";
  return (
    <div className="relative px-5 py-4 flex-1 min-w-[160px] group">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="font-mono text-[10px] uppercase tracking-loose2 text-ink-400">
          {label}
        </span>
        {hint && (
          <span className="font-mono text-[9px] uppercase tracking-loose2 text-ink-500">
            {hint}
          </span>
        )}
      </div>
      <div className={`font-display text-[2rem] leading-none tabular-nums font-medium ${color}`}
           style={{ fontVariationSettings: '"opsz" 72, "SOFT" 60' }}>
        {value != null ? value.toFixed(2) : "—"}
      </div>
    </div>
  );
}

function SectorTile({ name, value }: { name: string; value: number | null }) {
  return (
    <div className="flex items-baseline justify-between gap-2 px-3 py-2 border-b border-rule-soft last:border-b-0">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-400">{name}</span>
      <span className="font-mono text-[12px] tabular-nums text-ink-100">
        {value != null ? value.toFixed(2) : "—"}
      </span>
    </div>
  );
}

export default function MarketContextStrip() {
  const { data } = useMarketContext();
  if (!data) {
    return (
      <div className="ledger-surface p-6 text-ink-500 text-sm font-mono">
        Awaiting tape…
      </div>
    );
  }

  const sectorEntries = Object.entries(data.sectors) as Array<[string, number | null]>;

  return (
    <div className="ledger-surface overflow-hidden">
      <div className="flex divide-x divide-rule">
        <Headline label="SPX" value={data.spx_last} hint="index" />
        <Headline label="QQQ" value={data.qqq_last} hint="tech" />
        <Headline label="VIX" value={data.vix_last} hint="vol" tone="warn" />
      </div>

      {sectorEntries.length > 0 && (
        <div className="border-t border-rule">
          <div className="px-5 py-2.5 border-b border-rule flex items-center gap-3 bg-ink-void/40">
            <span className="ledger-eyebrow">Sectors</span>
            <span className="flex-1 h-px bg-rule-soft" />
            <span className="font-mono text-[10px] text-ink-500">{sectorEntries.length} tracked</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            {sectorEntries.map(([k, v]) => (
              <SectorTile key={k} name={k} value={v} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
