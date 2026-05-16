import type { UserFile } from "../hooks/useFiles";

export function FileAttachPanel({
  threadId,
  files,
  onAttach,
}: {
  threadId: number;
  files: UserFile[];
  onAttach: (fileId: number) => void;
}) {
  if (files.length === 0) {
    return <p className="text-sm text-slate-400">No files yet — upload one above.</p>;
  }
  return (
    <ul className="flex flex-col gap-1" data-thread-id={threadId}>
      {files.map((f) => (
        <li key={f.id} data-testid={`file-row-${f.id}`} className="flex items-center gap-2 text-sm">
          <span className="text-slate-200">{f.filename || "(no name)"}</span>
          <span className="text-xs text-slate-500">{f.kind}</span>
          {f.ticker && <span className="text-xs text-slate-500">{f.ticker}</span>}
          <button
            className="ml-auto px-2 py-0.5 text-xs rounded bg-slate-700 text-slate-100"
            onClick={() => onAttach(f.id)}
          >
            Attach
          </button>
        </li>
      ))}
    </ul>
  );
}
