import { useCallback, useRef, useState } from "react";
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
 * events have arrived. The map is updated in-place and triggers a re-render on
 * every change.
 *
 * The HTTP poll in SnapshotComposerPage remains the terminal source of truth;
 * this hook is progress-only.
 */
export function useSnapshotProgress(snapshotId: number | null): SnapshotProgressState {
  // Use a ref-backed Map so we can mutate without cloning, but trigger a
  // re-render by bumping a counter whenever the map changes.
  const sectionsRef = useRef<Map<string, SectionStatus>>(new Map());
  const [, forceRender] = useState(0);

  const channel = snapshotId !== null ? `snapshot.${snapshotId}` : null;

  const handler = useCallback((msg: unknown) => {
    const ev = msg as Partial<SectionEvent>;
    if (ev.type !== "snapshot.section" || !ev.section || !ev.status) return;
    sectionsRef.current.set(ev.section, ev.status);
    forceRender((n) => n + 1);
  }, []);

  useChannel(channel, handler);

  return { sections: sectionsRef.current };
}
