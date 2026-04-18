import { ProviderLeaderboardCard } from "@/components/analytics/ProviderLeaderboardCard";
import { CostPerInsightCard } from "@/components/analytics/CostPerInsightCard";
import { TriggerHeatmapCard } from "@/components/analytics/TriggerHeatmapCard";
import { ObserverTimelineCard } from "@/components/analytics/ObserverTimelineCard";
import { UnusualOptionsCard } from "@/components/analytics/UnusualOptionsCard";

export default function AnalyticsPage() {
  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <header className="mb-8 pb-6 border-b border-rule">
        <span className="ledger-eyebrow">Analytics</span>
        <h1
          className="ledger-display"
          style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}
        >
          Last 30 days
        </h1>
      </header>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ProviderLeaderboardCard />
        <CostPerInsightCard />
        <TriggerHeatmapCard />
        <ObserverTimelineCard />
        <UnusualOptionsCard />
      </div>
    </main>
  );
}
