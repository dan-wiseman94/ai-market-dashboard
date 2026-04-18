import { useCallback } from "react";

export type Range = { from: string; to: string };
type Props = { value: Range; onChange: (r: Range) => void };

const PRESETS: Array<[string, string, number]> = [
  ["today", "Today", 1],
  ["7d", "Last 7 days", 7],
  ["30d", "Last 30 days", 30],
  ["month", "This month", -1], // calendar month
  ["last-month", "Last month", -2],
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
    <div className="flex items-center gap-2 text-sm">
      <label className="text-slate-500">
        Range:
        <select
          aria-label="Range preset"
          defaultValue="30d"
          onChange={(e) => onPreset(e.target.value)}
          className="ml-2 bg-slate-900 border border-slate-700 rounded px-2 py-1"
        >
          {PRESETS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          <option value="custom">Custom</option>
        </select>
      </label>
      <input
        type="datetime-local" aria-label="From"
        value={value.from ? value.from.slice(0, 16) : ""}
        onChange={(e) => onChange({ ...value, from: new Date(e.target.value).toISOString() })}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1"
      />
      <input
        type="datetime-local" aria-label="To"
        value={value.to ? value.to.slice(0, 16) : ""}
        onChange={(e) => onChange({ ...value, to: new Date(e.target.value).toISOString() })}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1"
      />
    </div>
  );
}
