import { useTriggerHeatmap } from "@/hooks/useAnalytics";
import { AnalyticsCard } from "./AnalyticsCard";
import { useTheme } from "@/hooks/useTheme";
import { rechartsColors } from "@/lib/chartTheme";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function TriggerHeatmapCard() {
  const q = useTriggerHeatmap();
  const colors = rechartsColors(useTheme().resolved);
  return (
    <AnalyticsCard testid="analytics-card-heatmap" title="Trigger fires (30d) · day × hour" query={q} wide>
      {(data) => {
        const max = Math.max(1, ...(data.cells ?? []).map((c) => c.count));
        return (
          <>
            <div
              className="grid gap-0.5"
              style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}
            >
              {(data.cells ?? []).map((c) => {
                const intensity = c.count / max;
                return (
                  <div
                    key={`${c.weekday}:${c.hour}`}
                    data-testid="heat-cell"
                    title={`${DAYS[c.weekday]} ${String(c.hour).padStart(2, "0")}:00 — ${c.count} fires`}
                    className="aspect-square rounded-sm"
                    style={{
                      background:
                        c.count === 0
                          ? colors.heatmapEmpty
                          : `rgba(200,150,88,${0.15 + 0.85 * intensity})`,
                    }}
                  />
                );
              })}
            </div>
            <p className="mt-3 text-xs text-slate-500 font-mono">
              Hottest cell: {Math.max(0, ...(data.cells ?? []).map((c) => c.count))} fires
            </p>
          </>
        );
      }}
    </AnalyticsCard>
  );
}
