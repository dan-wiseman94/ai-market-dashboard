import AiAttribution from "@/components/ai/AiAttribution";
import type { EvalRun } from "@/api/aieval";

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

/** Every persisted run, newest first. Selecting one drives the reliability table. */
export default function EvalRunsTable({
  runs, selectedId, onSelect,
}: {
  runs: EvalRun[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-ink-400">
            <th className="py-1 pr-3 font-normal">Run</th>
            <th className="py-1 pr-3 font-normal">Target</th>
            <th className="py-1 pr-3 font-normal">Label</th>
            <th className="py-1 pr-3 text-right font-normal">Scored</th>
            <th className="py-1 pr-3 text-right font-normal">Hit-rate</th>
            <th className="py-1 pr-3 text-right font-normal">Brier</th>
            <th className="py-1 text-right font-normal">Cal. err</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr
              key={r.id}
              data-testid={`eval-run-${r.id}`}
              className={`border-t border-rule ${r.id === selectedId ? "text-ink-100" : "text-ink-300"}`}
            >
              <td className="py-1.5 pr-3">
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  aria-pressed={r.id === selectedId}
                  className="text-copper-300 underline-offset-2 hover:text-copper-200 hover:underline"
                >
                  {new Date(r.created_at).toLocaleDateString()}
                </button>
              </td>
              <td className="py-1.5 pr-3">
                <AiAttribution provider={r.provider} model={r.model} />
              </td>
              <td className="py-1.5 pr-3 text-[12px] text-ink-400">
                {r.label} · {r.source}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums">
                {r.scored}/{r.n}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{pct(r.hit_rate)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{r.brier ?? "—"}</td>
              <td className="py-1.5 text-right tabular-nums">{pct(r.calibration_error)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
