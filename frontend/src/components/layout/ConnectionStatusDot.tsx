import { useHealth } from "@/hooks/useHealth";

export default function ConnectionStatusDot() {
  const healthState = useHealth();
  const color = healthState === "down" ? "bg-rose-500" : healthState === "loading" ? "bg-amber-400" : "bg-emerald-500";
  const title = healthState === "down" ? "Backend unreachable" : healthState === "loading" ? "Connecting…" : "Connected";
  return (
    <span title={title} aria-label={title} className={`inline-block w-2 h-2 rounded-full ${color}`} />
  );
}
