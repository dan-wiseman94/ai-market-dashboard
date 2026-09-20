import { useState } from "react";
import { providerLabel } from "@/api/ai";
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import Field from "@/components/settings/Field";
import { useCatalog, pickModelFor } from "@/hooks/useCatalog";
import { useTriggerEvalRun } from "@/hooks/useAieval";
import { useToast } from "@/hooks/useToast";
import { FALLBACK_HORIZONS } from "@/lib/horizons";

/** Queue one bounded, billed eval run on a chosen provider. */
export default function EvalRunForm({ onQueued }: { onQueued: () => void }) {
  const catalog = useCatalog();
  const trigger = useTriggerEvalRun();
  const { push } = useToast();

  const [target, setTarget] = useState({ provider: "claude", model: "" });
  const [horizon, setHorizon] = useState(30);
  const [limit, setLimit] = useState(25);
  const [label, setLabel] = useState("manual");

  // Resolve the model lazily so the form shows the catalog default as soon as it loads.
  const model = target.model || pickModelFor(target.provider, catalog);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await trigger.mutateAsync({ provider: target.provider, model, horizon, limit, label });
      push({ kind: "success", text: "Eval queued — it appears in the table when it finishes." });
      onQueued();
    } catch (err) {
      push({ kind: "error", text: (err as Error).message });
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
              value={String(horizon)}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="ledger-input w-full py-2 tabular-nums"
            >
              {FALLBACK_HORIZONS.map((h) => <option key={h} value={h}>{h}</option>)}
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

      <p className="text-[12px] text-copper-300">
        Makes up to {limit} billed calls on {providerLabel(target.provider)}. Skipped
        automatically if that provider&apos;s cost cap is hit.
      </p>

      <button type="submit" disabled={trigger.isPending} className="ledger-cta">
        {trigger.isPending ? "Queueing…" : "Queue eval"}
      </button>
    </form>
  );
}
