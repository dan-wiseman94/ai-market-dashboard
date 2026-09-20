import ProviderSelect from "@/components/ai/ProviderSelect";
import ModelSelect from "@/components/settings/ModelSelect";
import { pickModelFor, useCatalog } from "@/hooks/useCatalog";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";

export type AiTarget = { provider: string; model: string };

type Props = {
  value: AiTarget;
  onChange: (v: AiTarget) => void;
  /** Adds an "inherit" first option; picking it emits { provider: "", model: "" }. */
  inherit?: { label: string };
  facts?: boolean;
  providerLabel?: string;
  modelLabel?: string;
};

export default function AiTargetPicker({
  value, onChange, inherit, facts, providerLabel = "Provider", modelLabel = "Model",
}: Props) {
  const catalog = useCatalog();
  const { data: configs } = useProviderConfigs();
  const inheriting = inherit !== undefined && value.provider === "";
  const discovered = configs?.find((c) => c.provider === "local")?.discovered_models ?? [];
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,200px)_1fr]">
      <ProviderSelect
        ariaLabel={providerLabel}
        value={value.provider}
        emptyOption={inherit?.label}
        onChange={(provider) =>
          onChange(provider === "" ? { provider: "", model: "" } : { provider, model: pickModelFor(provider, catalog) })}
      />
      {!inheriting && (
        <ModelSelect
          ariaLabel={modelLabel}
          provider={value.provider}
          value={value.model}
          models={value.provider === "local" && discovered.length > 0 ? discovered : undefined}
          onChange={(model) => onChange({ ...value, model })}
          facts={facts}
        />
      )}
    </div>
  );
}
