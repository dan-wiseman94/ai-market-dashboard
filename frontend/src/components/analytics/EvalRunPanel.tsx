import { useId, useState } from "react";

import { ApiError } from "@/api/client";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  useEvalRuns,
  useQueueEvalRun,
  type EvalProvider,
  type EvalRunQueued,
  type EvalRunRequest,
} from "@/hooks/useAnalytics";
import { useSystemSettings } from "@/hooks/useSystemSettings";
import type { SystemSettings } from "@/api/settings";
import { useToast } from "@/hooks/useToast";

const PROVIDERS: readonly EvalProvider[] = ["claude", "openai", "local"];
const HORIZONS = ["7", "30", "90", "all"] as const;

/** Fallbacks used only until GET /api/settings/ lands (or if it fails). */
const FALLBACK_HORIZON = "30";
const FALLBACK_LIMIT = 25;

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

interface RunRow {
  id: number;
  created_at: string;
  model: string;
  horizon: number | null;
  scored: number;
  hit_rate: number | null;
  brier: number | null;
}

type Refusal = { tone: "warn" | "error"; text: string };

/**
 * Translate a failed queue attempt. 409 and 429 are refusals, not faults: the
 * backend deliberately declined and nothing was queued or billed. Everything
 * else is a real error.
 */
function refusalFor(err: unknown, provider: string): Refusal {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return {
        tone: "warn",
        text:
          "Not queued — the stack is in mock mode (MOCK_EXTERNAL). Real eval runs are " +
          "refused there because a mocked score would persist as a fabricated measurement " +
          `that the coach and router then read as real. Nothing was billed. (${err.message})`,
      };
    }
    if (err.status === 429) {
      return {
        tone: "warn",
        text:
          `Not queued — the monthly cost cap for ${provider} is already reached. Nothing was ` +
          `billed. Raise the cap or wait for the 30-day window to roll. (${err.message})`,
      };
    }
  }
  return {
    tone: "error",
    text: err instanceof Error ? err.message : "Could not queue the eval run.",
  };
}

function RunsTable({ rows, since }: { rows: readonly RunRow[]; since: number | null }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-ink-400">
          <th className="text-left">Run</th>
          <th className="text-left">Model</th>
          <th>Horizon</th>
          <th>Scored</th>
          <th>Hit-rate</th>
          <th>Brier</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const isNew = since !== null && Date.parse(r.created_at) >= since;
          return (
            <tr key={r.id} className="border-t border-rule">
              <td className={isNew ? "text-copper-300" : ""}>
                {new Date(r.created_at).toLocaleString()}
                {isNew && <span className="ml-1 text-xs">(this run)</span>}
              </td>
              <td>{r.model}</td>
              <td className="text-center">{r.horizon === null ? "all" : `${r.horizon}d`}</td>
              <td className="text-center">{r.scored}</td>
              <td className="text-center">{pct(r.hit_rate)}</td>
              <td className="text-center">{r.brier ?? "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

interface Params {
  provider: EvalProvider;
  model: string;
  horizon: string;
  limit: number;
}

function ParamsFieldset({
  params,
  onChange,
}: {
  params: Params;
  onChange: (patch: Partial<Params>) => void;
}) {
  const modelId = useId();
  const horizonId = useId();
  const limitId = useId();
  const limitHelpId = useId();
  const { provider, model, horizon, limit } = params;

  return (
    <fieldset className="grid grid-cols-1 gap-3 rounded border border-rule p-3 sm:grid-cols-4">
      <legend className="px-1 text-xs uppercase tracking-wide text-ink-500">
        Eval parameters
      </legend>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-ink-500">Provider</span>
        <select
          value={provider}
          onChange={(e) => onChange({ provider: e.target.value as EvalProvider })}
          className="rounded border border-rule bg-ink-900 px-2 py-1 text-ink-100"
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm sm:col-span-2" htmlFor={modelId}>
        <span className="text-xs text-ink-500">Model</span>
        <input
          id={modelId}
          type="text"
          value={model}
          onChange={(e) => onChange({ model: e.target.value })}
          placeholder={provider === "local" ? "required for local" : "provider default"}
          className="rounded border border-rule bg-ink-900 px-2 py-1 font-mono text-[12px] text-ink-100"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor={horizonId}>
        <span className="text-xs text-ink-500">Horizon</span>
        <select
          id={horizonId}
          value={horizon}
          onChange={(e) => onChange({ horizon: e.target.value })}
          className="rounded border border-rule bg-ink-900 px-2 py-1 text-ink-100"
        >
          {HORIZONS.map((h) => (
            <option key={h} value={h}>
              {h === "all" ? "every horizon" : `${h}d`}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor={limitId}>
        <span className="text-xs text-ink-500">Snapshots</span>
        <input
          id={limitId}
          type="number"
          min={1}
          max={200}
          value={limit}
          aria-describedby={limitHelpId}
          onChange={(e) => onChange({ limit: Number(e.target.value) })}
          className="rounded border border-rule bg-ink-900 px-2 py-1 tabular-nums text-ink-100"
        />
      </label>
      <p id={limitHelpId} className="text-xs text-ink-500 sm:col-span-3 sm:self-end">
        Upper bound on replayed snapshots, so the bill is bounded too — 1 to 200. Defaults come
        from the scheduled-eval settings.
      </p>
    </fieldset>
  );
}

/** The explicit "this costs money" gate. Nothing is POSTed until it is accepted. */
function ConfirmPanel({
  params,
  onCancel,
  onConfirm,
}: {
  params: Params;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      data-testid="eval-run-confirm"
      className="mt-3 rounded border border-copper-700 p-3 text-sm"
    >
      <p className="text-ink-200">
        This costs real money. Up to {params.limit} replayed snapshots × 1 billed{" "}
        {params.provider} call each
        {params.model ? ` on ${params.model}` : ""}, charged to your own API key. It cannot be
        undone or refunded once queued.
      </p>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-rule px-3 py-1 text-ink-300 hover:text-ink-100"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="rounded border border-copper-600 px-3 py-1 text-copper-200 hover:bg-copper-900/30"
        >
          Yes, spend money and run it
        </button>
      </div>
    </div>
  );
}

/** Honest about a fire-and-forget 202: "queued" until the row actually lands. */
function QueuedBanner({ queued, landed }: { queued: EvalRunQueued; landed: boolean }) {
  return (
    <p data-testid="eval-run-queued" role="status" className="mt-3 text-sm text-ink-400">
      Queued as task <span className="font-mono text-[12px]">{queued.task_id}</span> —{" "}
      {queued.provider}/{queued.model}, {queued.limit} snapshots, horizon{" "}
      {queued.horizon === null ? "all" : `${queued.horizon}d`}.{" "}
      {landed
        ? "The run has landed — it is the highlighted row below."
        : "Queued is not finished: the worker reports no completion event, so this list re-reads every 15s until the run appears."}
    </p>
  );
}

function RecentRuns({
  rows,
  isLoading,
  since,
}: {
  rows: readonly RunRow[];
  isLoading: boolean;
  since: number | null;
}) {
  return (
    <div className="mt-4">
      <h3 className="mb-2 text-sm font-medium text-ink-200">Recent eval runs</h3>
      {isLoading ? (
        <SkeletonRows rows={3} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No eval runs yet"
          body="Queue one above, or run manage.py aieval for an unbounded replay."
        />
      ) : (
        <RunsTable rows={rows} since={since} />
      )}
    </div>
  );
}

/**
 * The parameters an eval will actually run with: the user's edits, falling back
 * to the configured scheduled-eval settings, falling back to a constant while
 * GET /api/settings/ is still in flight. Derived at render — never copied into
 * state by an effect.
 */
function resolveParams(edits: Partial<Params>, settings: SystemSettings | undefined): Params {
  const model = edits.model ?? settings?.aieval_scheduled_model ?? "";
  const horizon = edits.horizon ?? String(settings?.aieval_scheduled_horizon ?? FALLBACK_HORIZON);
  const limit = edits.limit ?? settings?.aieval_scheduled_limit ?? FALLBACK_LIMIT;
  return { provider: edits.provider ?? "claude", model, horizon, limit };
}

function buildRequest(params: Params): EvalRunRequest {
  const model = params.model.trim();
  return {
    provider: params.provider,
    horizon: params.horizon === "all" ? null : Number(params.horizon),
    limit: params.limit,
    ...(model ? { model } : {}),
  };
}

/**
 * Queue a calibration eval run and watch for it to land.
 *
 * Lives on the Scorecard because this is where EvalRun data is already
 * rendered ("Model eval calibration"): the control that produces a row sits
 * next to the rows it produces. The Analytics page shows cost/latency
 * aggregates and no EvalRun at all.
 *
 * POST /api/aieval/runs/ is fire-and-forget — a 202 with a task id and no
 * completion event — so the UI says "queued", never "done", and polls the run
 * list until the new row appears.
 */
export function EvalRunPanel() {
  const { data: settings } = useSystemSettings();
  const { push } = useToast();
  const queue = useQueueEvalRun();

  // null = "inherit the configured default"; the settings fetch is async, so the
  // effective value is derived at render rather than copied in via an effect.
  const [edits, setEdits] = useState<Partial<Params>>({});
  const [confirming, setConfirming] = useState(false);
  const [queued, setQueued] = useState<EvalRunQueued | null>(null);
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const runs = useEvalRuns(queuedAt);
  const rows: RunRow[] = runs.data ?? [];
  const landed = queuedAt !== null && rows.some((r) => Date.parse(r.created_at) >= queuedAt);

  const params = resolveParams(edits, settings);

  // A local endpoint serves user-declared model names, so there is no catalog
  // default to fall back to — the backend rejects the body without one.
  const needsModel = params.provider === "local" && params.model.trim() === "";

  const costId = useId();

  function submit() {
    const body = buildRequest(params);
    setConfirming(false);
    setRefusal(null);
    queue.mutate(body, {
      onSuccess: (data) => {
        setQueued(data);
        setQueuedAt(Date.now());
        push({ kind: "info", text: "Eval run queued." });
      },
      onError: (err) => {
        const r = refusalFor(err, params.provider);
        setRefusal(r);
        push({ kind: r.tone === "warn" ? "info" : "error", text: r.text });
      },
    });
  }

  return (
    <section data-testid="eval-run-panel">
      <h2 className="mb-2 font-semibold">Run a calibration eval</h2>
      <p className="mb-3 text-sm text-ink-400" id={costId}>
        Replays frozen past snapshots through a candidate model and scores its directional
        calls — the measurement behind the card above. This spends real money: one billed
        model call per replayed snapshot, on your own API key. There is no mocked path.
      </p>

      <ParamsFieldset params={params} onChange={(patch) => setEdits({ ...edits, ...patch })} />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={confirming || queue.isPending || needsModel}
          aria-describedby={costId}
          className="rounded border border-copper-600 px-3 py-1.5 text-sm text-copper-200 transition-colors hover:bg-copper-900/30 disabled:opacity-50"
        >
          {queue.isPending ? "Queuing…" : "Run eval…"}
        </button>
        {needsModel && (
          <span className="text-xs text-ink-400">
            A local endpoint has no catalog default — name the model first.
          </span>
        )}
      </div>

      {confirming && (
        <ConfirmPanel
          params={params}
          onCancel={() => setConfirming(false)}
          onConfirm={submit}
        />
      )}

      {refusal && (
        <p
          data-testid="eval-run-refusal"
          role="alert"
          className={`mt-3 text-sm ${refusal.tone === "warn" ? "text-copper-400" : "text-loss"}`}
        >
          {refusal.text}
        </p>
      )}

      {queued && <QueuedBanner queued={queued} landed={landed} />}

      <RecentRuns rows={rows} isLoading={runs.isLoading} since={queuedAt} />
    </section>
  );
}
