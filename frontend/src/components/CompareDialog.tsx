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
    <div
      className="fixed inset-0 z-50 grid place-items-center ledger-fade-in"
      style={{ background: "color-mix(in srgb, var(--ink-void) 80%, transparent)", backdropFilter: "blur(4px)" }}
      onClick={onCancel}
    >
      <div
        className="ledger-surface max-w-2xl w-full mx-4 p-0 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-6 py-4 border-b border-rule">
          <div className="ledger-eyebrow mb-1">Parallel Consultation</div>
          <h2 className="font-display text-2xl text-ink-50 tracking-tight2">
            Ask <em className="text-copper-300 italic">each house</em>.
          </h2>
        </header>

        <div className="px-6 py-5 space-y-4">
          <textarea
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Your question to every branch…"
            className="ledger-input w-full font-display text-[15px]"
            style={{ fontVariationSettings: '"opsz" 18' }}
          />

          <div className="space-y-2">
            <div className="ledger-eyebrow">Branches</div>
            {branches.map((b, i) => (
              <div key={i} className="flex items-center gap-3">
                <span className="font-mono text-[10px] text-copper-400 w-6 shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="flex-1">
                  <ProviderModelPicker
                    value={b}
                    onChange={(v) => {
                      const next = [...branches]; next[i] = v; setBranches(next);
                    }}
                  />
                </div>
                {branches.length > 1 && (
                  <button
                    className="font-mono text-[10px] text-ink-500 hover:text-loss transition-colors uppercase tracking-wider"
                    onClick={() => setBranches(branches.filter((_, j) => j !== i))}
                  >
                    remove
                  </button>
                )}
              </div>
            ))}
          </div>

          <button
            className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors uppercase tracking-wider"
            onClick={() => setBranches([...branches, { provider: "claude", model: "claude-sonnet-4-6" }])}
          >
            + add branch
          </button>
        </div>

        <footer className="px-6 py-4 border-t border-rule flex justify-end gap-3">
          <button onClick={onCancel} className="ledger-ghost">Cancel</button>
          <button
            onClick={() => { if (text.trim() && branches.length) onSubmit(text.trim(), branches); }}
            className="ledger-cta"
          >
            <span>Dispatch to {branches.length} branch{branches.length === 1 ? "" : "es"}</span>
            <span aria-hidden className="font-mono text-[11px] opacity-70">↗</span>
          </button>
        </footer>
      </div>
    </div>
  );
}
