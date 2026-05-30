import { useCallback, useState } from "react";
import { useChannel } from "@/hooks/useChannel";

export type SectionStatus = "running" | "done" | "failed";

export type SnapshotProgressState = {
  /** Map from section kind (e.g. "quotes") to its latest status. */
  sections: Map<string, SectionStatus>;
};

type SectionEvent = {
  type: "snapshot.section";
  section: string;
  status: SectionStatus;
};

/**
 * Subscribe to the snapshot.<id> WS channel and collect per-section
 * capture-progress events into a section→status map.
 *
 * Returns an empty map when snapshotId is null (not yet created) or when no
 * events have arrived. The map is replaced on each change to trigger a
 * re-render while keeping the consumer API stable.
 *
 * The HTTP poll in SnapshotComposerPage remains the terminal source of truth;
 * this hook is progress-only.
 */
export function useSnapshotProgress(snapshotId: number | null): SnapshotProgressState {
  // Keep sections in state so reads during render never touch a ref.
  // We replace the Map reference on each update so React sees a new value and
  // re-renders, while the spread clone is cheap (typically <10 entries).
  const [sections, setSections] = useState<Map<string, SectionStatus>>(() => new Map());

  const channel = snapshotId !== null ? `snapshot.${snapshotId}` : null;

  const handler = useCallback((msg: unknown) => {
    const ev = msg as Partial<SectionEvent>;
    if (ev.type !== "snapshot.section" || !ev.section || !ev.status) return;
    setSections((prev) => new Map(prev).set(ev.section!, ev.status!));
  }, []);

  useChannel(channel, handler);

  return { sections };
}
