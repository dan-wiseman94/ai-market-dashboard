import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useCalibration,
  useCalibrationDrilldown,
  useLatestEvalRun,
} from "@/hooks/useAnalytics";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

const HORIZONS = [7, 30, 90] as const;

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

export default function ScorecardPage() {
  const [horizon, setHorizon] = useState<number>(30);
  const [selected, setSelected] = useState<number | null>(null);
  const { data, isLoading } = useCalibration(90, horizon);
  const { data: drill, isLoading: drillLoading } = useCalibrationDrilldown(selected, horizon, 90);
  const { data: evalRun } = useLatestEvalRun();

  function pickHorizon(h: number) {
    setHorizon(h);
    setSelected(null); // a bucket selected at one horizon doesn't carry to another
  }

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Calibration scorecard</h1>
        <div className="flex gap-1 text-sm">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => pickHorizon(h)}
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
            <p className="mb-2 text-xs text-ink-500">
              Select a conviction to see the theses behind it.
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400">
                  <th className="text-left">Conviction</th>
                  <th>n</th>
                  <th>Hit-rate</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.thesis.buckets.map((b) => (
                  <tr key={b.conviction} className="border-t border-rule">
                    <td>
                      {b.n > 0 ? (
                        <button
                          onClick={() =>
                            setSelected(selected === b.conviction ? null : b.conviction)
                          }
                          aria-expanded={selected === b.conviction}
                          className="text-copper-300 underline-offset-2 hover:text-copper-200 hover:underline"
                        >
                          {b.conviction}
                        </button>
                      ) : (
                        b.conviction
                      )}
                    </td>
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

            {selected !== null && (
              <div className="mt-3 rounded border border-rule p-3">
                <p className="mb-2 text-sm text-ink-400">
                  Conviction {selected} — theses behind this bucket
                </p>
                {drillLoading ? (
                  <SkeletonRows rows={3} />
                ) : !drill || drill.rows.length === 0 ? (
                  <EmptyState title="No theses in this bucket" />
                ) : (
                  <ul className="space-y-1 text-sm">
                    {drill.rows.map((r) => (
                      <li
                        key={r.thesis_id}
                        className="flex items-center justify-between gap-3 border-t border-rule pt-1 first:border-t-0"
                      >
                        <Link
                          to={`/theses/${r.thesis_id}`}
                          className="truncate text-ink-100 hover:text-copper-300"
                        >
                          {r.ticker} · {r.title}
                        </Link>
                        <span className="flex shrink-0 items-center gap-3 text-ink-400">
                          <span>{r.direction}</span>
                          <span>{r.verdict}</span>
                          <span
                            className={r.forward_return_pct >= 0 ? "text-gain-400" : "text-loss-400"}
                          >
                            {r.forward_return_pct >= 0 ? "+" : ""}
                            {r.forward_return_pct.toFixed(1)}%
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
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
                    <th className="text-left">Provider</th>
                    <th className="text-left">Model</th>
                    <th>n</th>
                    <th>Hit-rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.provider.map((r) => (
                    <tr key={`${r.provider}-${r.model}`} className="border-t border-rule">
                      <td>{r.provider}</td>
                      <td>{r.model}</td>
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

      {/* Measured model calibration from the offline eval harness (M7) — independent
          of thesis post-mortems, so it renders whenever an eval run exists. */}
      {evalRun && evalRun.scored > 0 && (
        <section>
          <h2 className="mb-2 font-semibold">Model eval calibration</h2>
          <p className="mb-2 text-sm text-ink-400">
            How often {evalRun.model}'s directional call was right on replayed past snapshots, vs how
            confident it claimed to be.
          </p>
          <p className="mb-3 text-sm text-ink-400">
            Hit-rate {pct(evalRun.hit_rate)} · Brier {evalRun.brier ?? "—"} · {evalRun.scored} scored
            · avg confidence {pct(evalRun.avg_confidence)}
          </p>
          {evalRun.calibration.filter((b) => b.n > 0).length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400">
                  <th className="text-left">Stated confidence</th>
                  <th>n</th>
                  <th>Observed</th>
                  <th>Stated</th>
                </tr>
              </thead>
              <tbody>
                {evalRun.calibration
                  .filter((b) => b.n > 0)
                  .map((b) => (
                    <tr key={`${b.bin_low}-${b.bin_high}`} className="border-t border-rule">
                      <td>
                        {(b.bin_low * 100).toFixed(0)}–{(b.bin_high * 100).toFixed(0)}%
                      </td>
                      <td className="text-center">{b.n}</td>
                      <td className="text-center">{pct(b.observed_hit_rate)}</td>
                      <td className="text-center">{pct(b.mean_confidence)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
