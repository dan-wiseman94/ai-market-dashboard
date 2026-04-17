import { Link } from "react-router-dom";
import { useCostsToday } from "@/hooks/useCosts";

export default function CostChip() {
  const { data } = useCostsToday();
  const total = Number(data?.total_usd ?? "0");
  return (
    <Link to="/costs" className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300">
      today: ${total.toFixed(4)}
    </Link>
  );
}
