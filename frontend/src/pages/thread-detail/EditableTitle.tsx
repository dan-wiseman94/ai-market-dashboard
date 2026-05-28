import { useState } from "react";

type Props = {
  title: string;
  onSave: (title: string) => void;
  pending?: boolean;
};

/** Thread masthead title with click-to-rename. Display mode shows the title (or
 * a placeholder) with a hover-revealed Rename affordance; edit mode is an input
 * committed on Enter/Save and abandoned on Escape/Cancel. */
export default function EditableTitle({ title, onSave, pending }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  if (!editing) {
    return (
      <div className="flex items-center gap-3 group/title">
        <h1 className="ledger-display" style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}>
          {title || <em className="italic text-copper-300">Untitled consultation</em>}
        </h1>
        <button
          type="button"
          onClick={() => {
            setDraft(title);
            setEditing(true);
          }}
          aria-label="Rename thread"
          data-testid="rename-thread-btn"
          className="opacity-0 group-hover/title:opacity-100 focus:opacity-100 transition-opacity font-mono text-[11px] uppercase tracking-wider text-ink-400 hover:text-copper-300"
        >
          ✎ Rename
        </button>
      </div>
    );
  }

  const commit = () => {
    onSave(draft.trim());
    setEditing(false);
  };

  return (
    <div className="flex items-center gap-2">
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") setEditing(false);
        }}
        maxLength={200}
        aria-label="Thread title"
        data-testid="rename-thread-input"
        placeholder="Untitled consultation"
        className="ledger-input flex-1 font-display text-[1.25rem]"
      />
      <button
        type="button"
        onClick={commit}
        disabled={pending}
        data-testid="rename-thread-save"
        className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider disabled:opacity-40"
      >
        Save
      </button>
      <button
        type="button"
        onClick={() => setEditing(false)}
        className="font-mono text-[11px] uppercase tracking-wider text-ink-400 hover:text-copper-300 transition-colors"
      >
        Cancel
      </button>
    </div>
  );
}
