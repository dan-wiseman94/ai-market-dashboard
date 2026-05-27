import { useState } from "react";

export interface ToolCallRecord {
  toolUseId: string;
  name: string;
  input: unknown;
  ok: boolean;
  error?: string;
  latencyMs: number;
  result?: unknown;
}

export function ToolCallTrace({ calls }: { calls: ToolCallRecord[] }) {
  if (calls.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 my-2 text-xs font-mono">
      {calls.map((c) => <Row key={c.toolUseId} c={c} />)}
    </div>
  );
}

function compact(obj: unknown): string {
  if (obj == null) return "";
  try {
    const s = JSON.stringify(obj);
    return s.length > 80 ? s.slice(0, 77) + "…" : s;
  } catch {
    return String(obj);
  }
}

function Row({ c }: { c: ToolCallRecord }) {
  const [open, setOpen] = useState(false);
  const tone = c.ok
    ? "text-sky-700 border-sky-300/60 dark:text-sky-300 dark:border-sky-800"
    : "text-rose-700 border-rose-300/60 dark:text-rose-300 dark:border-rose-800";
  return (
    <div className={`border rounded px-2 py-1 bg-slate-900/40 ${tone}`}>
      <button
        className="flex gap-2 items-center w-full text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="font-semibold">{c.name}</span>
        <span className="text-slate-400 truncate">{compact(c.input)}</span>
        <span className="ml-auto text-slate-500">{c.latencyMs} ms</span>
        {!c.ok && <span className="text-rose-700 dark:text-rose-400">✗ {c.error}</span>}
      </button>
      {open && (
        <pre className="mt-1 text-[11px] text-slate-300 whitespace-pre-wrap">
          input: {JSON.stringify(c.input, null, 2)}
          {"\n"}
          result: {JSON.stringify(c.result, null, 2)}
        </pre>
      )}
    </div>
  );
}
