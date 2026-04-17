import { useHealth } from "@/hooks/useHealth";

export default function App() {
  const health = useHealth();

  const label =
    health === "loading"
      ? "Checking…"
      : health === "ok"
        ? "Stack is green"
        : "Stack is down";

  const tone =
    health === "loading"
      ? "text-slate-400"
      : health === "ok"
        ? "text-emerald-400"
        : "text-rose-400";

  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-semibold">AI Trading Dashboard</h1>
        <p className={`text-lg ${tone}`}>{label}</p>
      </div>
    </main>
  );
}
