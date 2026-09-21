import { useId, useState } from "react";
import { providerLabel } from "@/api/ai";
import { ApiError } from "@/api/client";
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import Field from "@/components/settings/Field";
import { useCatalog, pickModelFor } from "@/hooks/useCatalog";
import { useTriggerEvalRun } from "@/hooks/useAieval";
import { useToast } from "@/hooks/useToast";
import { FALLBACK_HORIZONS } from "@/lib/horizons";

type Refusal = { tone: "warn" | "error"; text: string };

/**
 * Translate a failed queue attempt. The endpoint answers 409 for BOTH of its
 * deliberate refusals and tells them apart by `code`, not by status — so read
 * the code, or a capped run reads as a mock-mode one. A refusal is not a fault:
 * nothing was queued and nothing was billed.
 */
function refusalFor(err: unknown, provider: string): Refusal {
  if (err instanceof ApiError) {
    if (err.code === "mock_mode") {
      return {
        tone: "warn",
        text:
          "Not queued — the stack is in mock mode (MOCK_EXTERNAL). Real eval runs are refused " +
          "there because a mocked score would persist as a fabricated measurement that the " +
          `coach and router then read as real. Nothing was billed. (${err.message})`,
      };
    }
    if (err.code === "cost_cap") {
      return {
        tone: "warn",
        text:
          `Not queued — the cost cap for ${providerLabel(provider)} is already reached. Nothing ` +
          `was billed. Raise the cap or wait for the window to roll. (${err.message})`,
      };
    }
  }
  return {
    tone: "error",
    text: err instanceof Error ? err.message : "Could not queue the eval run.",
  };
}

/** Queue one bounded, billed eval run on a chosen provider. */
export default function EvalRunForm({ onQueued }: { onQueued: () => void }) {
  const catalog = useCatalog();
  const trigger = useTriggerEvalRun();
  const { push } = useToast();

  const [target, setTarget] = useState({ provider: "claude", model: "" });
  // "all" posts horizon: null — the serializer reads an explicit null as
  // "score every configured horizon" rather than as an omitted field.
  const [horizon, setHorizon] = useState("30");
  const [limit, setLimit] = useState(25);
  const [label, setLabel] = useState("manual");
  const [system, setSystem] = useState("");
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const systemHintId = useId();

  // Resolve the model lazily so the form shows the catalog default as soon as it loads.
  const model = target.model || pickModelFor(target.provider, catalog);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setRefusal(null);
    const prompt = system.trim();
    try {
      await trigger.mutateAsync({
        provider: target.provider,
        model,
        horizon: horizon === "all" ? null : Number(horizon),
        limit,
        label,
        // Only sent when written, so the run keeps the harness's own prompt.
        ...(prompt ? { system: prompt } : {}),
      });
      push({ kind: "success", text: "Eval queued — it appears in the table when it finishes." });
      onQueued();
    } catch (err) {
      const r = refusalFor(err, target.provider);
      setRefusal(r);
      push({ kind: r.tone === "warn" ? "info" : "error", text: r.text });
    }
  };

  return (
    <form onSubmit={submit} className="ledger-surface space-y-3 p-4">
      <AiTargetPicker
        value={{ provider: target.provider, model }}
        onChange={setTarget}
        providerLabel="Provider"
        modelLabel="Model"
        facts
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Horizon (days)">
          {({ id }) => (
            <select
              id={id}
              aria-label="Horizon (days)"
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
              className="ledger-input w-full py-2 tabular-nums"
            >
              {FALLBACK_HORIZONS.map((h) => <option key={h} value={String(h)}>{h}</option>)}
              <option value="all">every horizon</option>
            </select>
          )}
        </Field>
        <Field label="Row limit">
          {({ id }) => (
            <input
              id={id}
              aria-label="Row limit"
              inputMode="numeric"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value.replace(/\D/g, "")) || 0)}
              // The API accepts 1–100; clamp here so the warning line never promises
              // "up to 0 billed calls" and the submit can't 400 on a bound.
              onBlur={(e) =>
                setLimit(Math.min(100, Math.max(1, Number(e.target.value.replace(/\D/g, "")))))
              }
              className="ledger-input w-full py-2 tabular-nums"
            />
          )}
        </Field>
        <Field label="Label">
          {({ id }) => (
            <input
              id={id}
              aria-label="Label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="ledger-input w-full py-2"
            />
          )}
        </Field>
      </div>

      <Field label="System prompt override (optional)">
        {({ id }) => (
          <textarea
            id={id}
            aria-label="System prompt override (optional)"
            aria-describedby={systemHintId}
            value={system}
            rows={3}
            onChange={(e) => setSystem(e.target.value)}
            placeholder="Leave blank for the harness's own prompt."
            className="ledger-input w-full py-2 font-mono text-[12px]"
          />
        )}
      </Field>
      <p id={systemHintId} className="text-[11px] text-ink-500">
        A/B a prompt against the same frozen snapshots: leave it blank for the default, or
        write one to score that prompt instead.
      </p>

      <p className="text-[12px] text-copper-300">
        Makes up to {limit} billed calls on {providerLabel(target.provider)}, charged to your own
        API key and not refundable once queued. Skipped automatically if that provider&apos;s cost
        cap is hit.
      </p>

      {refusal && (
        <p
          data-testid="eval-run-refusal"
          role="alert"
          className={`text-[12px] ${refusal.tone === "warn" ? "text-copper-400" : "text-loss"}`}
        >
          {refusal.text}
        </p>
      )}

      <button type="submit" disabled={trigger.isPending} className="ledger-cta">
        {trigger.isPending ? "Queueing…" : "Queue eval"}
      </button>
    </form>
  );
}
