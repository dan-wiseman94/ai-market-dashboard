import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useClearProfileMemory, useProfileMemory } from "@/hooks/useProfiles";
import { useToast } from "@/hooks/useToast";
import { fmtSize, formatRelative } from "@/utils/format";
import type { MemoryEntry } from "@/api/profiles";

/** What the model stands to lose, spelled out before anything is deleted. */
function clearMemoryConfirm(totalFiles: number, totalBytes: number): string {
  const files = `${totalFiles} file${totalFiles === 1 ? "" : "s"} (${fmtSize(totalBytes)})`;
  return (
    `Clear this profile's memory?\n\n` +
    `${files} will be deleted from disk. This cannot be undone: the model loses that ` +
    `context permanently and later runs of this profile start from an empty store.`
  );
}

function EntryRow({ entry }: { entry: MemoryEntry }) {
  return (
    <li className="rounded border border-slate-800 bg-slate-900/60 p-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-xs text-slate-200">{entry.path}</span>
        <span className="text-xs tabular-nums text-slate-500">
          {fmtSize(entry.size_bytes)} · {formatRelative(entry.modified_at)}
        </span>
      </div>
      <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-400">
        {entry.preview}
        {entry.preview_truncated && <span className="text-slate-600">… (truncated)</span>}
      </pre>
    </li>
  );
}

/**
 * What Claude's Memory tool has stored for this profile, and the control that
 * wipes it.
 *
 * The store is written by the model out of turns that carry untrusted DATA
 * (snapshots, news, filings, tool output — see the data-boundary directive in
 * apps/threads/coach.py), and it is re-read on every later run of this profile.
 * The previews are the point: a bare file list would not let anyone spot text
 * that was injected into the model and then saved.
 */
export function MemoryPanel({ profileId }: { profileId: number | null }) {
  const { data, isLoading, isError } = useProfileMemory(profileId);
  const clear = useClearProfileMemory();
  const { push } = useToast();

  const onClear = () => {
    if (profileId === null || !data) return;
    if (!window.confirm(clearMemoryConfirm(data.total_files, data.total_bytes))) return;
    clear.mutate(profileId, {
      onSuccess: (res) =>
        push({
          kind: "success",
          text: `Memory cleared — ${res.removed_files} file${
            res.removed_files === 1 ? "" : "s"
          }, ${fmtSize(res.removed_bytes)} deleted.`,
        }),
      onError: () => push({ kind: "error", text: "Could not clear the memory store." }),
    });
  };

  return (
    <section
      aria-label="Memory store"
      className="ml-6 space-y-2 rounded border border-slate-800 bg-slate-900/40 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Memory store
        </h3>
        {data && data.total_files > 0 && (
          <span className="text-xs tabular-nums text-slate-400">
            {data.total_files} file{data.total_files === 1 ? "" : "s"} ·{" "}
            {fmtSize(data.total_bytes)}
          </span>
        )}
      </div>

      {profileId === null ? (
        <p className="text-xs text-slate-500">
          Save this profile to see what its memory holds. Memory persists across every run of
          the profile and is written by the model itself.
        </p>
      ) : isLoading ? (
        <SkeletonRows rows={2} />
      ) : isError ? (
        <p role="alert" className="text-xs text-rose-400">
          Could not read the memory store.
        </p>
      ) : data && data.entries.length > 0 ? (
        <>
          <p className="text-xs text-slate-500">
            The model wrote these itself and re-reads them on every later run of this profile.
            Snapshots, news, filings and tool output reach it as untrusted data, so read these
            for instructions that are not yours.
          </p>
          <ul className="space-y-2">
            {data.entries.map((e) => (
              <EntryRow key={e.path} entry={e} />
            ))}
          </ul>
          <button
            type="button"
            onClick={onClear}
            disabled={clear.isPending}
            aria-label="Clear memory store"
            className="rounded border border-rose-800 px-2 py-1 text-xs text-rose-300 hover:bg-rose-950 disabled:opacity-50"
          >
            {clear.isPending ? "Clearing…" : "Clear memory"}
          </button>
        </>
      ) : (
        <EmptyState
          title="Nothing stored yet"
          body="Memory persists across every run of this profile and is written by the model itself — anything it saves here comes back on every later run."
        />
      )}
    </section>
  );
}
