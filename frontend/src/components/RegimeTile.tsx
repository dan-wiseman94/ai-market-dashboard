import { Link } from "react-router-dom";

export interface DashboardRegime {
  composite: string | null;
  drivers: string[];
  as_of: string | null;
}

// Theme-adaptive: dark: variants keep these readable in light mode too (the
// fixed -600 weights were tuned for the dark theme only). ink/copper are tokens.
const TONE: Record<string, string> = {
  "Risk-On": "text-emerald-700 dark:text-emerald-400",
  "Neutral-Transitional": "text-ink",
  "Risk-Off": "text-copper",
  Stress: "text-red-700 dark:text-red-400",
};

export function RegimeTile({ regime }: { regime: DashboardRegime }) {
  return (
    <Link to="/regime" className="block rounded border border-rule p-4 hover:bg-ink/5">
      <div className="text-xs uppercase tracking-wide text-ink/60">Market regime</div>
      {regime.composite ? (
        <>
          <div className={`mt-1 text-xl font-bold ${TONE[regime.composite] ?? "text-ink"}`}>
            {regime.composite}
          </div>
          {regime.drivers[0] && <div className="mt-1 text-sm text-ink/70">{regime.drivers[0]}</div>}
        </>
      ) : (
        <div className="mt-1 text-sm text-ink/60">No reading yet</div>
      )}
    </Link>
  );
}
