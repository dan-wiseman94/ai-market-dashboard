import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";

const CUSTOM = "__custom__";

type Props = {
  provider: string;
  value: string;
  onChange: (model: string) => void;
  id?: string;
  describedBy?: string;
};

export default function ModelSelect({ provider, value, onChange, id, describedBy }: Props) {
  const { data } = useAiModels(provider);
  const models: AiModel[] = (data?.models ?? []).filter((m) => m.provider === provider);
  const known = models.some((m) => m.id === value);
  const showCustom = !known;

  return (
    <div className="space-y-2">
      <select
        id={id}
        aria-describedby={describedBy}
        value={showCustom ? CUSTOM : value}
        onChange={(e) => onChange(e.target.value === CUSTOM ? "" : e.target.value)}
        className="ledger-input w-full py-2"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
        <option value={CUSTOM}>Custom…</option>
      </select>
      {showCustom && (
        <input
          aria-label="Custom model id"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g. llama-3.1-70b"
          className="ledger-input w-full py-2 font-mono text-[12px]"
        />
      )}
    </div>
  );
}
