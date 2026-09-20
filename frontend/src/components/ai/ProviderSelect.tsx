import { PROVIDER_IDS, PROVIDER_LABEL, type ProviderConfig, type ProviderId } from "@/api/ai";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";

type Props = {
  value: string;
  onChange: (provider: string) => void;
  id?: string;
  ariaLabel?: string;
  describedBy?: string;
  /** When set, a first option with this label emits "" (e.g. "Inherit from profile", "None"). */
  emptyOption?: string;
  className?: string;
};

/** One-word readiness for a provider row: ready / no key / no base URL / disabled. */
export function providerReadiness(cfg: ProviderConfig | undefined, provider: ProviderId): string {
  if (!cfg) return provider === "local" ? "no base URL" : "no key";
  if (!cfg.enabled) return "disabled";
  if (provider === "local") return cfg.base_url ? "ready" : "no base URL";
  return cfg.api_key_present ? "ready" : "no key";
}

export default function ProviderSelect({ value, onChange, id, ariaLabel, describedBy, emptyOption, className }: Props) {
  const { data: configs } = useProviderConfigs();
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`ledger-input py-2 ${className ?? ""}`}
    >
      {emptyOption !== undefined && <option value="">{emptyOption}</option>}
      {PROVIDER_IDS.map((p) => (
        <option key={p} value={p}>
          {PROVIDER_LABEL[p]} · {providerReadiness(configs?.find((c) => c.provider === p), p)}
        </option>
      ))}
    </select>
  );
}
