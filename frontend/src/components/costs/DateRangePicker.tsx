import { useCallback } from "react";

export type Range = { from: string; to: string };
type Props = { value: Range; onChange: (r: Range) => void };

const PRESETS: Array<[value: string, label: string]> = [
  ["today", "Today"],
  ["7d", "Last 7 days"],
  ["30d", "Last 30 days"],
  ["month", "This month"],
  ["last-month", "Last month"],
];

function computeRange(preset: string): Range {
  const now = new Date();
  const to = now.toISOString();
  if (preset === "today") {
    const start = new Date(now); start.setHours(0, 0, 0, 0);
    return { from: start.toISOString(), to };
  }
  if (preset === "month") {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: start.toISOString(), to };
  }
  if (preset === "last-month") {
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const end = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: start.toISOString(), to: end.toISOString() };
  }
  const days = Number(preset.replace("d", ""));
  const start = new Date(now.getTime() - days * 86400000);
  return { from: start.toISOString(), to };
}

export default function DateRangePicker({ value, onChange }: Props) {
  const onPreset = useCallback((preset: string) => onChange(computeRange(preset)), [onChange]);

  return (
    <div className="ledger-surface px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <span className="ledger-eyebrow">Range</span>
      <label>
        <span className="sr-only">Range preset</span>
        <select
          aria-label="Range preset"
          defaultValue="30d"
          onChange={(e) => onPreset(e.target.value)}
          className="ledger-input py-1 text-[12px] font-mono"
        >
          {PRESETS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          <option value="custom">Custom</option>
        </select>
      </label>
      <span className="font-mono text-[10px] text-ink-500">from</span>
      <input
        type="datetime-local" aria-label="From"
        value={value.from ? value.from.slice(0, 16) : ""}
        onChange={(e) => onChange({ ...value, from: new Date(e.target.value).toISOString() })}
        className="ledger-input py-1 text-[12px] font-mono"
      />
      <span className="font-mono text-[10px] text-ink-500">to</span>
      <input
        type="datetime-local" aria-label="To"
        value={value.to ? value.to.slice(0, 16) : ""}
        onChange={(e) => onChange({ ...value, to: new Date(e.target.value).toISOString() })}
        className="ledger-input py-1 text-[12px] font-mono"
      />
    </div>
  );
}
