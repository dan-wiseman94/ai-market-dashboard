import { PROVIDER_IDS, PROVIDER_LABEL } from "@/api/ai";
import { pickModelFor, useCatalog } from "@/hooks/useCatalog";

type Value = { provider: string; model: string };
type Props = { value: Value; onChange: (v: Value) => void };

/** Compact provider + model picker for the thread composer and Compare dialog. */
export default function ProviderModelPicker({ value, onChange }: Props) {
  const catalog = useCatalog();
  const modelsForProvider = catalog.modelsFor(value.provider);
  return (
    <div className="flex gap-2 text-[12px]">
      <select
        aria-label="Provider"
        value={value.provider}
        onChange={(e) => {
          const provider = e.target.value;
          onChange({ provider, model: pickModelFor(provider, catalog) });
        }}
        className="ledger-input py-1 pr-6 text-[12px] font-mono uppercase tracking-wider"
      >
        {PROVIDER_IDS.map((p) => <option key={p} value={p}>{PROVIDER_LABEL[p]}</option>)}
      </select>
      <select
        aria-label="Model"
        value={value.model}
        onChange={(e) => onChange({ ...value, model: e.target.value })}
        className="ledger-input flex-1 py-1 pr-6 text-[12px] font-mono"
      >
        {modelsForProvider.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {modelsForProvider.length === 0 && (
          <option value={value.model}>(no catalog models — type your own)</option>
        )}
      </select>
      {modelsForProvider.length === 0 && (
        <input
          aria-label="Model id"
          value={value.model}
          onChange={(e) => onChange({ ...value, model: e.target.value })}
          placeholder="model id"
          className="ledger-input flex-1 py-1 text-[12px] font-mono"
        />
      )}
    </div>
  );
}
