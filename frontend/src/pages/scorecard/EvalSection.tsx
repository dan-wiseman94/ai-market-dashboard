import { useEffect, useRef, useState } from "react";
import type { EvalRun } from "@/api/aieval";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useEvalRuns } from "@/hooks/useAieval";
import EvalRunForm from "./EvalRunForm";
import EvalRunsTable from "./EvalRunsTable";

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

/** How well a run's stated confidence matched its observed hit-rate. */
function EvalCalibration({ evalRun }: { evalRun: EvalRun }) {
  const bins = evalRun.calibration.filter((b) => b.n > 0);
  return (
    <section className="mt-4">
      <h3 className="mb-2 font-semibold">Model eval calibration</h3>
      <p className="mb-2 text-sm text-ink-400">
        How often {evalRun.model}&apos;s directional call was right on replayed past snapshots, vs
        how confident it claimed to be.
      </p>
      <p className="mb-3 text-sm text-ink-400">
        Hit-rate {pct(evalRun.hit_rate)} · Brier {evalRun.brier ?? "—"} · {evalRun.scored} scored
        · avg confidence {pct(evalRun.avg_confidence)}
      </p>
      {bins.length > 0 && (
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
            {bins.map((b) => (
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
  );
}

function RunHistory({
  runs, isLoading, selectedId, onSelect,
}: {
  runs: EvalRun[] | undefined;
  isLoading: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  if (isLoading) return <SkeletonRows rows={3} />;
  if (!runs || runs.length === 0) {
    return (
      <EmptyState
        title="No eval runs yet"
        body="Run one to measure a model's calibration on replayed snapshots."
      />
    );
  }
  return <EvalRunsTable runs={runs} selectedId={selectedId} onSelect={onSelect} />;
}

/** Poll the run list only while a queued run is expected to land. A run that hasn't
 * appeared within the window isn't coming, so the polling stops on its own. */
function usePollWhilePending(windowMs: number) {
  const [pending, setPending] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const start = () => {
    setPending(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPending(false), windowMs);
  };
  return [pending, start] as const;
}

/** The offline eval harness: run history across providers, and the control that
 * queues a new run. This is where a provider A/B is actually compared. */
export default function EvalSection({ latest }: { latest: EvalRun | undefined }) {
  const [polling, startPolling] = usePollWhilePending(3 * 60_000);
  const { data: runs, isLoading } = useEvalRuns({ refetchInterval: polling ? 15_000 : false });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const selected = runs?.find((r) => r.id === selectedId) ?? latest ?? runs?.[0];

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Offline eval</h2>
        <button type="button" className="ledger-ghost" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Close" : "Run eval"}
        </button>
      </div>
      <p className="mb-3 text-sm text-ink-400">
        Replays frozen snapshots of decisive theses through a model and scores its directional
        calls. Compare providers here before trusting one.
      </p>

      {showForm && <EvalRunForm onQueued={startPolling} />}

      <div className="mt-3">
        <RunHistory
          runs={runs}
          isLoading={isLoading}
          selectedId={selected?.id ?? null}
          onSelect={setSelectedId}
        />
      </div>

      {selected && selected.scored > 0 && <EvalCalibration evalRun={selected} />}
    </section>
  );
}
