const SECTIONS = [
  { key: "quotes", label: "Quotes" },
  { key: "ohlc", label: "OHLC bars" },
  { key: "positions", label: "Positions" },
  { key: "breadth", label: "Market context" },
  { key: "notes", label: "My notes" },
];

type Props = { value: string[]; onChange: (next: string[]) => void };

export default function SnapshotSectionPicker({ value, onChange }: Props) {
  const toggle = (k: string) =>
    onChange(value.includes(k) ? value.filter((v) => v !== k) : [...value, k]);
  return (
    <div className="flex flex-wrap gap-2">
      {SECTIONS.map((s) => (
        <label key={s.key} className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={value.includes(s.key)} onChange={() => toggle(s.key)} />
          {s.label}
        </label>
      ))}
    </div>
  );
}
