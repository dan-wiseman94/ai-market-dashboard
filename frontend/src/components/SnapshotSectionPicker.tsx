import { SECTION_KINDS, SECTION_LABELS } from "@/lib/snapshotSections";

type Props = { value: string[]; onChange: (next: string[]) => void };

export default function SnapshotSectionPicker({ value, onChange }: Props) {
  const toggle = (k: string) =>
    onChange(value.includes(k) ? value.filter((v) => v !== k) : [...value, k]);
  return (
    <div className="flex flex-wrap gap-2">
      {SECTION_KINDS.map((k) => (
        <label key={k} className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={value.includes(k)} onChange={() => toggle(k)} />
          {SECTION_LABELS[k]}
        </label>
      ))}
    </div>
  );
}
