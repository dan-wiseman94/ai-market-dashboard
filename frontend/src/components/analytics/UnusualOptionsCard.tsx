import { useState } from "react";
import { useUnusualOptions } from "@/hooks/useAnalytics";

export function UnusualOptionsCard() {
  const [ticker, setTicker] = useState("");
  const { data, isLoading, error } = useUnusualOptions(ticker.toUpperCase());
  return (
    <section data-testid="analytics-card-unusual-options" className="ledger-surface p-5 md:col-span-2">
      <header className="ledger-eyebrow mb-3">Unusual options</header>
      <input
        className="w-32 px-2 py-1 mb-3 bg-slate-900 border border-slate-700 rounded text-sm font-mono text-slate-100"
        placeholder="Ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
      />
      {!ticker && (
        <p className="text-sm text-slate-400">Enter a ticker to scan.</p>
      )}
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{String(error)}</p>}
      {data && data.rows.length === 0 && (
        <p className="text-sm text-slate-500">
          No unusual lines in the latest chain.
        </p>
      )}
      {data && data.rows.length > 0 && (
        <table className="w-full text-sm font-mono">
          <thead>
            <tr className="text-slate-400 text-left">
              <th>Expiry</th><th>Side</th><th>Strike</th>
              <th>Vol/OI</th><th>IV z</th><th>Why</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-800">
                <td>{r.expiry}</td>
                <td>{r.side}</td>
                <td>{r.strike}</td>
                <td>{r.volume_ratio.toFixed(2)}</td>
                <td>{r.iv_z == null ? "—" : r.iv_z.toFixed(2)}</td>
                <td>{r.triggers.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
