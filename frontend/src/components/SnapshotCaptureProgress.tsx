import type { SectionStatus } from "@/hooks/useSnapshotProgress";

const STATUS_ICON: Record<SectionStatus, string> = {
  done: "✓",
  running: "⏳",
  failed: "✗",
};

const STATUS_CLASS: Record<SectionStatus, string> = {
  done: "text-emerald-400",
  running: "text-amber-400",
  failed: "text-red-400",
};

type Props = {
  sections: Map<string, SectionStatus>;
};

/**
 * Renders a per-section capture-progress checklist.
 *
 * Each entry shows: <icon> <section-name>
 *   done    → ✓ (green)
 *   running → ⏳ (amber)
 *   failed  → ✗ (red)
 *
 * Returns null when the sections map is empty so the composer page has no
 * extra chrome before a snapshot is created.
 */
export function SnapshotCaptureProgress({ sections }: Props) {
  if (sections.size === 0) return null;

  return (
    <ul
      aria-label="Capture progress"
      className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
    >
      {Array.from(sections.entries()).map(([section, status]) => (
        <li key={section} className={`flex items-center gap-1 ${STATUS_CLASS[status]}`}>
          <span aria-hidden="true">{STATUS_ICON[status]}</span>
          <span className="text-slate-300">{section}</span>
        </li>
      ))}
    </ul>
  );
}
