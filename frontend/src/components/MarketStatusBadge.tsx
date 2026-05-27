// frontend/src/components/MarketStatusBadge.tsx
import { useMarketStatus } from "@/hooks/useMarketStatus";
import { sessionKind, SESSION_LABEL, type SessionKind } from "@/lib/marketSession";

const DOT: Record<SessionKind, string> = {
  open: "bg-emerald-400",
  extended: "bg-amber-400",
  closed: "bg-slate-500",
};

export default function MarketStatusBadge() {
  const { data } = useMarketStatus();
  const markets = data?.markets ?? {};
  const keys = Object.keys(markets);
  if (keys.length === 0) return null;

  const openCount = keys.filter((k) => markets[k].is_open).length;
  const tip = keys
    .map((k) => `${k}: ${markets[k].phase ?? (markets[k].is_open ? "open" : "closed")}`)
    .join(", ");

  let label: string;
  let dot: string;
  if (keys.length === 1) {
    const kind = sessionKind(markets[keys[0]]);
    label = SESSION_LABEL[kind];
    dot = DOT[kind];
  } else {
    label = `${openCount}/${keys.length} open`;
    dot = openCount > 0 ? DOT.open : DOT.closed;
  }

  return (
    <span data-testid="market-status" title={tip} className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
      <span>{label}</span>
    </span>
  );
}
