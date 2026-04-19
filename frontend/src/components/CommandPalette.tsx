import { useEffect, useMemo, useState } from "react";

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

  useEffect(() => {
    if (!open) {
      setQ("");
      setIdx(0);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim();
    if (!needle) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(needle) ||
        (c.keywords ?? "").toLowerCase().includes(needle),
    );
  }, [q, commands]);

  useEffect(() => {
    setIdx(0);
  }, [q]);

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
        className="w-[560px] max-w-[90vw] bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <input
          autoFocus
          placeholder="Search commands…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full px-4 py-3 bg-transparent text-slate-100 outline-none border-b border-slate-700"
        />
        <ul className="max-h-[400px] overflow-y-auto">
          {filtered.map((c, i) => (
            <li
              key={c.id}
              className={`px-4 py-2 cursor-pointer ${i === idx ? "bg-slate-800" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => {
                c.run();
                onClose();
              }}
            >
              <span className="text-slate-100">{c.label}</span>
              {c.keywords && (
                <span className="ml-2 text-xs text-slate-500">{c.keywords}</span>
              )}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-slate-500">No commands match.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
