import { useState } from "react";
import ProviderModelPicker from "./ProviderModelPicker";

type Branch = { provider: string; model: string };
type Props = {
  onCancel: () => void;
  onSubmit: (text: string, branches: Branch[]) => void;
};

export default function CompareDialog({ onCancel, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [branches, setBranches] = useState<Branch[]>([
    { provider: "claude", model: "claude-sonnet-4-6" },
    { provider: "openai", model: "gpt-5-mini" },
  ]);

  return (
    <div className="fixed inset-0 bg-black/70 grid place-items-center z-50">
      <div className="bg-slate-950 border border-slate-700 rounded p-4 max-w-xl w-full space-y-3">
        <h2 className="text-lg font-medium">Compare across providers</h2>
        <textarea
          rows={3} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Message to send to each branch…"
          className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        {branches.map((b, i) => (
          <div key={i} className="flex items-center gap-2">
            <ProviderModelPicker value={b} onChange={(v) => {
              const next = [...branches]; next[i] = v; setBranches(next);
            }} />
            {branches.length > 1 && (
              <button className="text-xs text-rose-400 hover:underline"
                      onClick={() => setBranches(branches.filter((_, j) => j !== i))}>
                remove
              </button>
            )}
          </div>
        ))}
        <div className="flex justify-between">
          <button className="text-sm text-slate-300 hover:underline"
                  onClick={() => setBranches([...branches, { provider: "claude", model: "claude-sonnet-4-6" }])}>
            + branch
          </button>
          <div className="flex gap-2">
            <button onClick={onCancel} className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm">
              Cancel
            </button>
            <button
              onClick={() => { if (text.trim() && branches.length) onSubmit(text.trim(), branches); }}
              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-sm"
            >
              Send to {branches.length} branches
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
