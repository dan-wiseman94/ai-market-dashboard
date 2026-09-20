import ModelFacts from "@/components/ai/ModelFacts";
import { useCatalog } from "@/hooks/useCatalog";

const CUSTOM = "__custom__";

type Props = {
  provider: string;
  value: string;
  onChange: (model: string) => void;
  id?: string;
  ariaLabel?: string;
  describedBy?: string;
  models?: string[]; // explicit id list (used for local discovery); overrides the catalog
  /** Render price / context / payload facts for the selected id below the select. */
  facts?: boolean;
};

export default function ModelSelect({
  provider, value, onChange, id, ariaLabel, describedBy, models: explicit, facts,
}: Props) {
  const { modelsFor } = useCatalog();
  const options: { id: string; name: string }[] = explicit
    ? explicit.map((m) => ({ id: m, name: m }))
    : modelsFor(provider).map((m) => ({ id: m.id, name: m.name }));
  const known = options.some((o) => o.id === value);
  const showCustom = !known;

  return (
    <div className="space-y-2">
      <select
        id={id}
        aria-label={ariaLabel}
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
      {facts && <ModelFacts provider={provider} modelId={value} />}
    </div>
  );
}
