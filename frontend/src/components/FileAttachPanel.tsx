import { EmptyState } from "@/components/EmptyState";
import type { UserFile } from "@/hooks/useFiles";

function kb(bytes: number): string {
  if (!bytes) return "";
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * The uploaded-file list for a thread: attach a file to the conversation, or
 * delete it outright.
 *
 * `attachDisabledReason` is set when the thread's provider cannot read
 * documents — attachments are Claude-only, and a non-Claude run drops the
 * document block and emits a capability warning instead. Rendering the reason
 * beats offering a button that silently does nothing.
 *
 * `onDelete` is optional so the existing prop-only render sites keep working;
 * when it is absent no delete control is offered.
 */
export function FileAttachPanel({
  threadId,
  files,
  onAttach,
  onDelete,
  attachDisabledReason,
}: {
  threadId: number;
  files: UserFile[];
  onAttach: (fileId: number) => void;
  onDelete?: (file: UserFile) => void;
  attachDisabledReason?: string;
}) {
  if (files.length === 0) {
    return (
      <EmptyState
        title="No files yet"
        body="Upload a filing, transcript or research PDF above, then attach it to this thread."
      />
    );
  }
  return (
    <ul className="flex flex-col gap-1" data-thread-id={threadId}>
      {files.map((f) => {
        const name = f.filename || "(no name)";
        return (
          <li
            key={f.id}
            data-testid={`file-row-${f.id}`}
            className="flex items-center gap-2 text-sm"
          >
            <span className="text-slate-200">{name}</span>
            <span className="text-xs text-slate-500">{f.kind}</span>
            {f.ticker && <span className="text-xs text-slate-500">{f.ticker}</span>}
            {f.size > 0 && <span className="text-xs text-slate-500">{kb(f.size)}</span>}
            <button
              type="button"
              className="ml-auto px-2 py-0.5 text-xs rounded bg-slate-700 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={() => onAttach(f.id)}
              disabled={!!attachDisabledReason}
              aria-label={`Attach ${name}`}
              title={attachDisabledReason || undefined}
            >
              Attach
            </button>
            {onDelete && (
              <button
                type="button"
                className="px-2 py-0.5 text-xs rounded border border-rule-soft text-loss"
                onClick={() => onDelete(f)}
                aria-label={`Delete ${name}`}
              >
                Delete
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
