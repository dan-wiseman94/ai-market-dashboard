import { useState } from "react";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";
import type { ObserverSchedule } from "@/api/observer";

export default function ScheduleSectionsEditor({
  schedule,
  onSave,
}: {
  schedule: ObserverSchedule;
  onSave: (includes: string[]) => void;
}) {
  const [includes, setIncludes] = useState<string[]>(schedule.default_includes ?? []);
  return (
    <div className="mt-2 space-y-2 border-t border-rule pt-2">
      {includes.length === 0 && (
        <div className="text-xs text-ink-500">
          Empty — inherits the profile&apos;s default sections.
        </div>
      )}
      <SnapshotSectionPicker value={includes} onChange={setIncludes} />
      <button type="button" onClick={() => onSave(includes)} className="ledger-cta">
        Save sections
      </button>
    </div>
  );
}
