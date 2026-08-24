import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useTraderCalibration } from "@/hooks/useAnalytics";
import { horizonsFrom } from "@/lib/horizons";

const DECISION_LABELS: Record<string, string> = {
  acted: "Acted",
  passed: "Passed",
  watching: "Watching",
  hedged: "Hedged",
};

const VERDICT_COPY: Record<string, string> = {
  inverted:
    "Inverted — your high-conviction calls have resolved WORSE than your hedged ones. Your certainty has been a contrarian signal.",
  flat: "Flat — conviction hasn't separated your winners from your losers. Your confidence isn't yet predictive.",
  aligned:
    "Aligned — your high-conviction calls do resolve better than your hedged ones. Your conviction is earning its weight.",
};

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

function readDecision(decision: string, hitRate: number): string {
  const high = hitRate >= 0.6;
  const low = hitRate <= 0.4;
  if (decision === "passed") {
    if (high) return "You've been passing on winners.";
    if (low) return "Good passes — these resolved against the call.";
  }
  if (decision === "acted") {
    if (high) return "Acting on the right calls.";
    if (low) return "Acting into losers.";
  }
  return "—";
}

export default function MirrorPage() {
  const [horizon, setHorizon] = useState<number>(30);
  const { data, isLoading } = useTraderCalibration(horizon);
  const decisions = data?.decision_outcomes;
  const conviction = data?.conviction_reliability;
  const horizons = horizonsFrom(data);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 ledger-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-100">The Mirror</h1>
          <p className="mt-1 text-sm text-ink-400 max-w-xl">
            The calibration engine, turned on you — how your own decisions and
            conviction have actually played out. Tendencies, with evidence; not
            verdicts.
          </p>
        </div>
        <div className="flex gap-1 text-sm">
          {horizons.map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded border border-rule px-2 py-1 transition-colors hover:text-copper-300 ${
                horizon === h ? "text-copper-300" : "text-ink-400"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <SkeletonRows rows={6} />
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Your decisions vs. outcomes
            </h2>
            {decisions?.status === "ok" ? (
              <table className="w-full text-sm">
                <thead className="text-ink-500">
                  <tr className="border-b border-rule text-left">
                    <th className="py-2 font-medium">When you…</th>
                    <th className="py-2 font-medium">Calls</th>
                    <th className="py-2 font-medium">Resolved correct</th>
                    <th className="py-2 font-medium">Read</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.buckets.map((b) => (
                    <tr key={b.decision} className="border-b border-rule">
                      <td className="py-2 text-ink-200">
                        {DECISION_LABELS[b.decision] ?? b.decision}
                      </td>
                      <td className="py-2 text-ink-400">{b.n}</td>
                      <td className="py-2 text-copper-200">
                        {b.correct}/{b.n} ({pct(b.hit_rate)})
                      </td>
                      <td className="py-2 text-ink-400">
                        {readDecision(b.decision, b.hit_rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState
                title="Not enough history yet"
                body="Journal more decisions on theses that reach a post-mortem, and this fills in."
              />
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Is your conviction predictive?
            </h2>
            {conviction?.status === "ok" ? (
              <>
                {conviction.verdict && (
                  <p className="text-sm text-copper-300">
                    {VERDICT_COPY[conviction.verdict] ?? conviction.verdict}
                  </p>
                )}
                <table className="w-full text-sm">
                  <thead className="text-ink-500">
                    <tr className="border-b border-rule text-left">
                      <th className="py-2 font-medium">Conviction</th>
                      <th className="py-2 font-medium">Calls</th>
                      <th className="py-2 font-medium">Hit rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conviction.buckets.map((b) => (
                      <tr key={b.conviction} className="border-b border-rule">
                        <td className="py-2 text-ink-200">{b.conviction}/5</td>
                        <td className="py-2 text-ink-400">{b.n}</td>
                        <td className="py-2 text-copper-200">{pct(b.hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <EmptyState
                title="Not enough history yet"
                body="Once enough theses reach a post-mortem, your conviction breakdown appears here."
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
