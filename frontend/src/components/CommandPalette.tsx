import { useMemo, useState } from "react";

export interface Command {
  id: string;
  label: string;
  keywords?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  // Reset transient state when the palette closes. Render-phase guarded update
  // (React's "adjust state when a prop changes" pattern) rather than an effect,
  // which avoids react-hooks/set-state-in-effect cascading renders.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!open) {
      setQ("");
      setIdx(0);
    }
  }

  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim();
    if (!needle) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(needle) ||
        (c.keywords ?? "").toLowerCase().includes(needle),
    );
  }, [q, commands]);

  if (!open) return null;

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      setIdx((i) => Math.min(filtered.length - 1, i + 1));
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setIdx((i) => Math.max(0, i - 1));
      e.preventDefault();
    } else if (e.key === "Enter") {
      const cmd = filtered[idx];
      if (cmd) {
        cmd.run();
        onClose();
      }
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center pt-24"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      data-testid="command-palette"
    >
      <div
        className="w-[560px] max-w-[90vw] bg-ink-900 border border-rule rounded-lg shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <input
          autoFocus
          placeholder="Search commands…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
          }}
          className="w-full px-4 py-3 bg-transparent text-ink-100 outline-none border-b border-rule"
        />
        <ul className="max-h-[400px] overflow-y-auto">
          {filtered.map((c, i) => (
            <li
              key={c.id}
              className={`px-4 py-2 cursor-pointer ${i === idx ? "bg-ink-800" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => {
                c.run();
                onClose();
              }}
            >
              <span className="text-ink-100">{c.label}</span>
              {c.keywords && (
                <span className="ml-2 text-xs text-ink-500">{c.keywords}</span>
              )}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink-500">No commands match.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
