import { Link } from "react-router-dom";
import { useCostsToday } from "@/hooks/useCosts";
import { usd } from "@/utils/format";

export default function CostChip() {
  const { data } = useCostsToday();
  return (
    <Link
      to="/costs"
      className="ledger-pill hover:border-copper-500/60 hover:text-copper-200 transition-colors"
      title="Today's AI spend — click to see costs"
    >
      <span className="text-ink-500">Today</span>
      <span className="tabular-nums text-ink-100">{usd(data?.total_usd ?? 0)}</span>
    </Link>
  );
}
