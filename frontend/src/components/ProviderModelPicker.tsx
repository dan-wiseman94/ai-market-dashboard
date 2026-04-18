import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";

type Value = { provider: string; model: string };
type Props = { value: Value; onChange: (v: Value) => void };

export default function ProviderModelPicker({ value, onChange }: Props) {
  const { data } = useAiModels();
  const all: AiModel[] = data?.models ?? [];
  const providers = Array.from(new Set(all.map((m) => m.provider)));
  const modelsForProvider = all.filter((m) => m.provider === value.provider);

  return (
    <div className="flex gap-2 text-[12px]">
      <select
        value={value.provider}
        onChange={(e) => {
          const provider = e.target.value;
          const firstModel = all.find((m) => m.provider === provider)?.id ?? "";
          onChange({ provider, model: firstModel });
        }}
        className="ledger-input py-1 pr-6 text-[12px] font-mono uppercase tracking-wider"
      >
        {providers.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select
        value={value.model}
        onChange={(e) => onChange({ ...value, model: e.target.value })}
        className="ledger-input flex-1 py-1 pr-6 text-[12px] font-mono"
      >
        {modelsForProvider.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {modelsForProvider.length === 0 && (
          <option value="">(no catalog models — type your own)</option>
        )}
      </select>
    </div>
  );
}
