import ProviderModelPicker from "@/components/ProviderModelPicker";

type ProviderModel = { provider: string; model: string };

type Props = {
  picker: ProviderModel;
  onPickerChange: (value: ProviderModel) => void;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCompare: () => void;
};

export default function Composer({
  picker,
  onPickerChange,
  input,
  onInputChange,
  onSend,
  onCompare,
}: Props) {
  return (
    <div
      className="mt-10 ledger-surface overflow-hidden"
      style={{ boxShadow: "0 -2px 40px -20px rgba(200,150,88,0.25)" }}
    >
      <div className="flex items-center gap-3 px-5 py-2.5 border-b border-rule-soft bg-ink-void/30">
        <span className="ledger-eyebrow">Reply with</span>
        <div className="flex-1">
          <ProviderModelPicker value={picker} onChange={onPickerChange} />
        </div>
        <button
          className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
          onClick={onCompare}
        >
          ⇌ Compare
        </button>
      </div>
      <form
        className="flex items-stretch"
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
      >
        <input
          data-testid="compose-input"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Continue the thread…"
          className="flex-1 px-5 py-4 bg-transparent border-0 focus:outline-none font-display text-[15px] text-ink-100 placeholder:text-ink-500"
          style={{ fontVariationSettings: '"opsz" 18' }}
        />
        <button className="ledger-cta rounded-none border-y-0 border-r-0 px-6">
          Send
          <span aria-hidden className="font-mono text-[11px] opacity-70">⏎</span>
        </button>
      </form>
    </div>
  );
}
