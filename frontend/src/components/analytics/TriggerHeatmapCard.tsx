import { useTriggerHeatmap } from "@/hooks/useAnalytics";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function TriggerHeatmapCard() {
  const { data, isLoading, error } = useTriggerHeatmap();
  const max = Math.max(1, ...(data?.cells ?? []).map((c) => c.count));
  return (
    <section data-testid="analytics-card-heatmap" className="ledger-surface p-5 md:col-span-2">
      <header className="ledger-eyebrow mb-3">
        Trigger fires (30d) · day × hour
      </header>
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{String(error)}</p>}
      {data && (
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
                        ? "rgba(255,255,255,0.04)"
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
      )}
    </section>
  );
}
