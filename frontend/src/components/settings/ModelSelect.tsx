import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";

const CUSTOM = "__custom__";

type Props = {
  provider: string;
  value: string;
  onChange: (model: string) => void;
  id?: string;
  describedBy?: string;
  models?: string[]; // explicit id list (used for local discovery); overrides the catalog
};

export default function ModelSelect({ provider, value, onChange, id, describedBy, models: explicit }: Props) {
  const { data } = useAiModels(provider);
  const options: { id: string; name: string }[] = explicit
    ? explicit.map((m) => ({ id: m, name: m }))
    : (data?.models ?? [])
        .filter((m: AiModel) => m.provider === provider)
        .map((m) => ({ id: m.id, name: m.name }));
  const known = options.some((o) => o.id === value);
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
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.name}</option>
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
