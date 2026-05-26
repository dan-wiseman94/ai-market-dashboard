// frontend/src/components/MarketStatusBadge.tsx
import { useMarketStatus } from "@/hooks/useMarketStatus";

export default function MarketStatusBadge() {
  const { data } = useMarketStatus();
  const markets = data?.markets ?? {};
  const keys = Object.keys(markets);
  if (keys.length === 0) return null;

  const openCount = keys.filter((k) => markets[k].is_open).length;
  const anyOpen = openCount > 0;
  const label =
    keys.length === 1 ? (markets[keys[0]].is_open ? "Open" : "Closed") : `${openCount}/${keys.length} open`;
  const tip = keys.map((k) => `${k}: ${markets[k].is_open ? "open" : "closed"}`).join(", ");

  return (
    <span data-testid="market-status" title={tip} className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`h-2 w-2 rounded-full ${anyOpen ? "bg-emerald-400" : "bg-slate-500"}`} />
      <span>{label}</span>
    </span>
  );
}
