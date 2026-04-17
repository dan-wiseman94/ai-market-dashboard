import MarketContextStrip from "@/components/MarketContextStrip";
import PositionsTable from "@/components/PositionsTable";
import { Link } from "react-router-dom";

export default function Dashboard() {
  return (
    <main className="p-6 max-w-6xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <nav className="text-sm space-x-4">
          <Link className="text-slate-300 hover:underline" to="/watchlists">Watchlists</Link>
          <Link className="text-slate-300 hover:underline" to="/settings">Settings</Link>
        </nav>
      </header>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-400 mb-2">Market context</h2>
        <MarketContextStrip />
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-400 mb-2">Positions</h2>
        <PositionsTable />
      </section>
    </main>
  );
}
