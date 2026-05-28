import SettingsSection from "@/components/settings/SettingsSection";
import ProviderCard from "@/components/settings/ProviderCard";

const PROVIDERS = ["claude", "openai", "local"] as const;

export default function ProvidersSettings() {
  return (
    <SettingsSection title="AI Providers" description="Keys, default models, and spend caps per provider.">
      {PROVIDERS.map((p) => <ProviderCard key={p} provider={p} />)}
    </SettingsSection>
  );
}
