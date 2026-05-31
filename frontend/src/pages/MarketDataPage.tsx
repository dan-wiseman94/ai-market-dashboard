import { useState, type FormEvent } from "react";
import { useMacro, useTreasury, useFilings } from "@/hooks/useMarketData";
import type { MacroSeries, Filing } from "@/api/market";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function MacroSection() {
  const { data, isLoading } = useMacro();
  const entries = Object.entries<MacroSeries>(data ?? {});
  return (
    <section className="mb-10">
      <h2 className="font-display text-[1.15rem] text-ink-50 mb-3">Macro indicators · FRED</h2>
      {isLoading ? (
        <p className="text-ink-400 text-sm">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-[13px] text-ink-400">
          No data yet — add a FRED key under Settings → Connections.
        </p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {entries.map(([sid, s]) => (
            <div key={sid} className="ledger-surface p-4" data-testid={`macro-${sid}`}>
              <div className="text-[12px] text-ink-400">{s.label}</div>
              <div className="font-display text-[1.25rem] text-ink-50 leading-tight">
                {fmt(s.value)}
              </div>
              <div className="mt-1 flex items-center gap-2">
                {s.change != null && (
                  <span className="ledger-pill" data-tone={s.change >= 0 ? "gain" : "loss"}>
                    {s.change >= 0 ? "+" : ""}
                    {fmt(s.change)}
                  </span>
                )}
                <span className="font-mono text-[10px] text-ink-500">{s.date}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function TreasurySection() {
  const { data, isLoading } = useTreasury();
  const rates = data?.rates?.rates ?? {};
  const debt = data?.debt;
  const hasData = Object.keys(rates).length > 0 || debt?.total_public_debt != null;
  return (
    <section className="mb-10">
      <h2 className="font-display text-[1.15rem] text-ink-50 mb-3">US Treasury</h2>
      {isLoading ? (
        <p className="text-ink-400 text-sm">Loading…</p>
      ) : !hasData ? (
        <p className="text-[13px] text-ink-400">No Treasury data right now.</p>
      ) : (
        <div className="ledger-surface p-5">
          {debt?.total_public_debt != null && (
            <div className="mb-4">
              <span className="text-[12px] text-ink-400">Total public debt</span>
              <div className="font-display text-[1.3rem] text-ink-50">
                ${fmt(debt.total_public_debt, 0)}
              </div>
              <span className="font-mono text-[10px] text-ink-500">{debt.record_date}</span>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
            {Object.entries<number>(rates).map(([desc, rate]) => (
              <div
                key={desc}
                className="flex items-baseline justify-between border-b border-rule-soft py-1"
              >
                <span className="text-[13px] text-ink-300">{desc}</span>
                <span className="font-mono text-[13px] text-ink-100">{fmt(rate)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function FilingsSection() {
  const [draft, setDraft] = useState("");
  const [tickers, setTickers] = useState<string[]>([]);
  const { data, isLoading } = useFilings(tickers);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setTickers(
      draft
        .split(",")
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean),
    );
  };

  return (
    <section>
      <h2 className="font-display text-[1.15rem] text-ink-50 mb-3">SEC filings · EDGAR</h2>
      <form onSubmit={onSubmit} className="flex gap-2 mb-4">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="AAPL, MSFT"
          aria-label="Tickers"
          className="ledger-input py-2 font-mono text-[13px] w-56"
        />
        <button type="submit" className="ledger-cta">
          Load filings
        </button>
      </form>
      {tickers.length === 0 ? (
        <p className="text-[13px] text-ink-400">Enter one or more tickers to list recent filings.</p>
      ) : isLoading ? (
        <p className="text-ink-400 text-sm">Loading…</p>
      ) : (
        <div className="space-y-5">
          {Object.entries<Filing[]>(data ?? {}).map(([ticker, filings]) => (
            <div key={ticker} data-testid={`filings-${ticker}`}>
              <h3 className="font-mono text-[12px] text-copper-300 mb-2">{ticker}</h3>
              {filings.length === 0 ? (
                <p className="text-[12px] text-ink-500">No recent filings.</p>
              ) : (
                <ul className="space-y-1">
                  {filings.map((f) => (
                    <li key={f.accession} className="flex items-baseline gap-3 text-[13px]">
                      <span className="font-mono text-[11px] text-copper-300 shrink-0 w-12">
                        {f.form}
                      </span>
                      <a
                        href={f.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-ink-200 hover:text-copper-300 truncate"
                      >
                        {f.title}
                      </a>
                      <span className="font-mono text-[11px] text-ink-500 ml-auto shrink-0">
                        {f.filed}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function MarketDataPage() {
  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <header className="mb-8 pb-6 border-b border-rule">
        <span className="ledger-eyebrow">Ledger · Market data</span>
        <h1 className="ledger-display mt-2" style={{ fontSize: "clamp(1.5rem, 2.6vw, 2.25rem)" }}>
          Macro, rates &amp; <em className="italic text-copper-300">filings</em>.
        </h1>
        <p className="mt-2 text-ink-300 text-[14px] max-w-2xl">
          Free data from FRED, the US Treasury, and SEC EDGAR — the same sources available as
          opt-in snapshot sections and under <code className="font-mono text-[12px]">/api/market/</code>.
        </p>
      </header>
      <MacroSection />
      <TreasurySection />
      <FilingsSection />
    </main>
  );
}
