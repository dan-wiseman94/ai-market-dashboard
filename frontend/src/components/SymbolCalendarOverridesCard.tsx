import { useState } from "react";
import {
  useCalendarOverrides,
  useCreateCalendarOverride,
  useDeleteCalendarOverride,
} from "@/hooks/useCalendarOverrides";
import type { MarketKey } from "@/api/market";

const MARKETS: Array<[MarketKey, string]> = [
  ["us_equity", "US equities (NYSE/NASDAQ)"],
  ["us_bond", "US bonds (SIFMA)"],
  ["cme_futures", "CME futures"],
  ["cfe_futures", "CFE / VIX futures"],
  ["crypto", "Digital assets (24/7)"],
  ["lse", "London (LSE)"],
  ["jpx", "Tokyo (JPX)"],
];

export default function SymbolCalendarOverridesCard() {
  const { data: overrides } = useCalendarOverrides();
  const create = useCreateCalendarOverride();
  const del = useDeleteCalendarOverride();
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState<MarketKey>("us_equity");

  return (
    <div className="p-4 rounded border border-slate-800 space-y-4">
      <div>
        <h2 className="text-lg font-medium">Symbol calendars</h2>
        <p className="text-xs text-slate-500">
          Override which market calendar a symbol uses. Unlisted symbols are auto-classified
          (NYSE by default).
        </p>
      </div>

      <ul className="space-y-1 text-sm">
        {(overrides ?? []).map((o) => (
          <li key={o.id} className="flex items-center justify-between border-t border-slate-800 pt-1">
            <span className="font-mono">{o.ticker}</span>
            <span className="text-slate-400">{o.market_key}</span>
            <button
              type="button"
              aria-label={`delete ${o.ticker}`}
              onClick={() => del.mutate(o.id)}
              className="px-2 py-0.5 text-xs rounded bg-red-900 hover:bg-red-800"
            >
              Delete
            </button>
          </li>
        ))}
      </ul>

      <form
        className="flex items-end gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ticker.trim()) return;
          create.mutate(
            { ticker: ticker.trim(), market_key: market },
            { onSuccess: () => setTicker("") },
          );
        }}
      >
        <input
          placeholder="Symbol (e.g. BTC-USD)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
        />
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-500">Market</span>
          <select
            aria-label="market"
            value={market}
            onChange={(e) => setMarket(e.target.value as MarketKey)}
            className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
          >
            {MARKETS.map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </label>
        <button type="submit" className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">
          Add
        </button>
      </form>
    </div>
  );
}
