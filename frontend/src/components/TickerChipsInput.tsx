import { useState, type KeyboardEvent } from "react";

type Props = {
  value: string[];
  onChange: (next: string[]) => void;
  /** Accessible name for the text input. */
  ariaLabel?: string;
  placeholder?: string;
};

// Permissive ticker shape: letters/digits plus the dot/hyphen used by share
// classes (BRK.B, RDS-A). Input that doesn't match is silently ignored rather
// than erroring — the user just keeps typing.
const TICKER_RE = /^[A-Z0-9.-]{1,10}$/;

/**
 * Controlled chips/tags input for ad-hoc ticker symbols. Type a ticker and
 * press Enter or comma to add it as a removable chip; symbols are uppercased
 * and de-duplicated against the existing value.
 */
export default function TickerChipsInput({
  value,
  onChange,
  ariaLabel = "Add tickers",
  placeholder = "e.g. SPY, AAPL",
}: Props) {
  const [draft, setDraft] = useState("");

  const commit = (raw: string) => {
    const ticker = raw.trim().toUpperCase();
    setDraft("");
    if (!TICKER_RE.test(ticker) || value.includes(ticker)) return;
    onChange([...value, ticker]);
  };

  const remove = (ticker: string) => onChange(value.filter((t) => t !== ticker));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 rounded bg-slate-900 border border-slate-700">
      {value.map((ticker) => (
        <span
          key={ticker}
          className="flex items-center gap-1 rounded bg-slate-800 border border-slate-600 px-1.5 py-0.5 text-xs"
        >
          {ticker}
          <button
            type="button"
            aria-label={`remove ${ticker}`}
            onClick={() => remove(ticker)}
            className="text-slate-400 hover:text-red-300 cursor-pointer leading-none"
          >
            ×
          </button>
        </span>
      ))}
      <input
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => commit(draft)}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[8ch] bg-transparent outline-none text-sm"
      />
    </div>
  );
}
