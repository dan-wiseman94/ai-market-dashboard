import SettingsSection from "@/components/settings/SettingsSection";
import ProviderCard from "@/components/settings/ProviderCard";
import ModelCatalogPanel from "@/components/settings/ModelCatalogPanel";
import { PROVIDER_IDS } from "@/api/ai";

export default function ProvidersSettings() {
  return (
    <SettingsSection
      title="AI Providers"
      description="Keys, endpoints, capabilities, default models and spend caps per provider."
    >
      {PROVIDER_IDS.map((p) => <ProviderCard key={p} provider={p} />)}
      <ModelCatalogPanel />
    </SettingsSection>
  );
}
