import ProviderConfigCard from "@/components/ProviderConfigCard";
import SchwabConnectionCard from "@/components/SchwabConnectionCard";

export default function Settings() {
  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <SchwabConnectionCard />
      <ProviderConfigCard />
    </main>
  );
}
