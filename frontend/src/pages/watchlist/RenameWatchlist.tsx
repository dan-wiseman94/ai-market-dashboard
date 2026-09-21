import { useState, type ReactNode } from "react";

type Props = {
  /** Current name — seeds the draft and names every control for screen readers. */
  name: string;
  onSave: (name: string) => void;
  pending?: boolean;
  /** Display-mode content: the name as a heading, a link, whatever the page wants. */
  children: ReactNode;
  className?: string;
};

/**
 * Inline click-to-rename for a watchlist, shared by the list rows and the detail
 * masthead. Display mode renders `children` next to a Rename button; edit mode
 * swaps in an input committed on Enter/Save and abandoned on Escape/Cancel.
 *
 * Every control carries the watchlist name in its accessible name — the list
 * renders one of these per row, and bare "Rename"/"Save" labels would be
 * indistinguishable to a screen reader.
 */
export function RenameWatchlist({ name, onSave, pending, children, className }: Props) {
  const [draft, setDraft] = useState<string | null>(null);

  if (draft === null) {
    return (
      <div className={`flex items-center gap-2 group/rename ${className ?? ""}`}>
        {children}
        <button
          type="button"
          onClick={() => setDraft(name)}
          aria-label={`Rename ${name}`}
          data-testid={`rename-watchlist-btn-${name}`}
          className="opacity-0 group-hover/rename:opacity-100 focus:opacity-100 transition-opacity font-mono text-[11px] uppercase tracking-wider text-ink-400 hover:text-copper-300"
        >
          ✎ Rename
        </button>
      </div>
    );
  }

  const commit = () => {
    const next = draft.trim();
    if (next && next !== name) onSave(next);
    setDraft(null);
  };

  return (
    <div className={`flex items-center gap-2 ${className ?? ""}`}>
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") setDraft(null);
        }}
        maxLength={120}
        aria-label={`New name for ${name}`}
        data-testid={`rename-watchlist-input-${name}`}
        className="flex-1 min-w-0 px-2 py-1 rounded bg-ink-900 border border-rule"
      />
      <button
        type="button"
        onClick={commit}
        disabled={pending}
        aria-label={`Save name for ${name}`}
        data-testid={`rename-watchlist-save-${name}`}
        className="font-mono text-[11px] uppercase tracking-wider text-ink-300 hover:text-copper-300 disabled:opacity-40"
      >
        Save
      </button>
      <button
        type="button"
        onClick={() => setDraft(null)}
        aria-label={`Cancel renaming ${name}`}
        className="font-mono text-[11px] uppercase tracking-wider text-ink-400 hover:text-copper-300"
      >
        Cancel
      </button>
    </div>
  );
}
