import { useState } from "react";
import { useCalibration } from "@/hooks/useAnalytics";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

const HORIZONS = [7, 30, 90] as const;

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

export default function ScorecardPage() {
  const [horizon, setHorizon] = useState<number>(30);
  const { data, isLoading } = useCalibration(90, horizon);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Calibration scorecard</h1>
        <div className="flex gap-1 text-sm">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded border border-rule px-2 py-1 transition-colors hover:text-copper-300 ${
                h === horizon ? "text-ink-100" : "text-ink-400"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {isLoading || !data ? (
        <SkeletonRows rows={6} />
      ) : data.thesis.overall.scored === 0 ? (
        <EmptyState
          title="No scored theses yet"
          body="Calibration sharpens as your theses reach their post-mortem horizon."
        />
      ) : (
        <>
          <section>
            <h2 className="mb-2 font-semibold">Thesis calibration</h2>
            <p className="mb-3 text-sm text-ink-400">
              Hit-rate {pct(data.thesis.overall.hit_rate)} · Brier{" "}
              {data.thesis.brier ?? "—"} · {data.thesis.overall.scored} scored ({horizon}d)
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400">
                  <th className="text-left">Conviction</th><th>n</th><th>Hit-rate</th><th></th>
                </tr>
              </thead>
              <tbody>
                {data.thesis.buckets.map((b) => (
                  <tr key={b.conviction} className="border-t border-rule">
                    <td>{b.conviction}</td>
                    <td className="text-center">{b.n}</td>
                    <td className="text-center">{pct(b.hit_rate)}</td>
                    <td className="w-1/2">
                      <div
                        className="h-2 rounded bg-copper-500"
                        style={{ width: `${(b.hit_rate ?? 0) * 100}%` }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2 className="mb-2 font-semibold">Provider calibration</h2>
            <p className="mb-2 text-sm text-ink-400">
              {data.attributable} of {data.scored} scored theses attributable to a provider.
            </p>
            {data.provider.length === 0 ? (
              <EmptyState title="No provider-attributable theses" />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-ink-400">
                    <th className="text-left">Provider</th><th className="text-left">Model</th>
                    <th>n</th><th>Hit-rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.provider.map((r) => (
                    <tr key={`${r.provider}-${r.model}`} className="border-t border-rule">
                      <td>{r.provider}</td><td>{r.model}</td>
                      <td className="text-center">{r.n}</td>
                      <td className="text-center">{pct(r.hit_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
