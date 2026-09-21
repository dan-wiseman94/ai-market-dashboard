import { providerLabel } from "@/api/ai";
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import InvestigateToggle from "@/components/schedule/InvestigateToggle";
import type { ObserverMode } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { useCatalog } from "@/hooks/useCatalog";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";

/** The seven fields that decide how a fire talks to a provider. */
export type AiFieldsValue = {
  override_provider: string;
  override_model: string;
  mode: ObserverMode;
  structured: boolean;
  use_batch: boolean;
  consensus: boolean;
  investigate: boolean;
};

/** A new schedule's defaults. `investigate` starts on, matching the model
 * default the observer writes for rows created outside the UI. */
export const BLANK_AI_FIELDS: AiFieldsValue = {
  override_provider: "",
  override_model: "",
  mode: "full",
  structured: false,
  use_batch: false,
  consensus: false,
  investigate: true,
};

/** Read a schedule row into the editor's shape, tolerating rows fetched before a
 * field existed (the page renders list payloads from several API versions). */
export function aiFieldsFrom(s: Partial<AiFieldsValue>): AiFieldsValue {
  return {
    override_provider: s.override_provider ?? "",
    override_model: s.override_model ?? "",
    mode: s.mode ?? "full",
    structured: s.structured ?? false,
    use_batch: s.use_batch ?? false,
    consensus: s.consensus ?? false,
    investigate: s.investigate ?? false,
  };
}

/** The provider/model a fire actually runs on, and where that came from.
 *
 * Mirrors the backend's own resolution (`run.py::_observer_model`): the schedule's
 * override, then the profile's model when the fire runs on the profile's own provider,
 * then the provider config's default, then the catalog default. Showing a different id
 * here than the one the fire uses would make the line worse than no line.
 */
export function effectiveTarget(
  v: Pick<AiFieldsValue, "override_provider" | "override_model">,
  profile: TradingProfile | undefined,
  defaultFor: (p: string) => string,
  configModel = "",
): { provider: string; model: string; qualifier: string } {
  const provider = v.override_provider || profile?.default_provider || "claude";
  const sameAsProfile = !v.override_provider || v.override_provider === profile?.default_provider;
  const model =
    v.override_model ||
    (sameAsProfile ? profile?.default_model : "") ||
    configModel ||
    defaultFor(provider);
  return { provider, model, qualifier: v.override_provider ? "override" : "from profile" };
}

function Check({
  id, label, checked, onToggle, disabled, hint,
}: {
  id: string;
  label: string;
  checked: boolean;
  onToggle: (v: boolean) => void;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <label className={`flex items-start gap-2 text-[13px] ${disabled ? "text-ink-500" : "text-ink-200"}`}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onToggle(e.target.checked)}
        className="mt-0.5"
      />
      <span>
        {label}
        {hint && <span className="block text-[11px] text-copper-300">{hint}</span>}
      </span>
    </label>
  );
}

export default function ScheduleAiFields({
  value, onChange, profile, idPrefix,
}: {
  value: AiFieldsValue;
  onChange: (v: AiFieldsValue) => void;
  profile: TradingProfile | undefined;
  idPrefix: string;
}) {
  const { defaultFor } = useCatalog();
  const { data: configs } = useProviderConfigs();
  const resolvedProvider = value.override_provider || profile?.default_provider || "claude";
  const configModel = configs?.find((c) => c.provider === resolvedProvider)?.default_model ?? "";
  const eff = effectiveTarget(value, profile, defaultFor, configModel);
  const isClaude = eff.provider === "claude";
  const set = (patch: Partial<AiFieldsValue>) => onChange({ ...value, ...patch });

  const inheritLabel = profile
    ? `Inherit from profile — ${providerLabel(profile.default_provider)} · ${
        profile.default_model || defaultFor(profile.default_provider)
      }`
    : "Inherit from profile";

  return (
    <fieldset className="space-y-3 rounded-ledger border border-rule p-3">
      <legend className="px-1 font-mono text-[10px] uppercase tracking-loose2 text-copper-400">
        AI
      </legend>

      <AiTargetPicker
        value={{ provider: value.override_provider, model: value.override_model }}
        onChange={(t) =>
          set({
            override_provider: t.provider,
            override_model: t.model,
            // Batches are Anthropic-only; dropping off Claude must clear the flag the
            // backend would reject.
            use_batch: value.use_batch && (t.provider || profile?.default_provider) === "claude",
          })
        }
        inherit={{ label: inheritLabel }}
        providerLabel="Override provider"
        modelLabel="Override model"
        facts
      />

      <label className="flex flex-col gap-1 text-[13px] text-ink-200">
        <span className="text-[11px] text-ink-400">Payload shape</span>
        <select
          id={`${idPrefix}-mode`}
          aria-label="Payload shape"
          value={value.mode}
          onChange={(e) => set({ mode: e.target.value as ObserverMode })}
          className="ledger-input py-2 sm:w-64"
        >
          <option value="full">Full payload</option>
          <option value="diff">Diff vs previous capture</option>
        </select>
      </label>

      <div className="grid gap-2 sm:grid-cols-2">
        <Check
          id={`${idPrefix}-structured`}
          label="Structured (typed observation card)"
          checked={value.structured}
          onToggle={(v) =>
            set({
              structured: v,
              consensus: v && value.consensus,
              investigate: v ? false : value.investigate,
            })
          }
        />
        <Check
          id={`${idPrefix}-consensus`}
          label="Cross-model consensus (fan the structured report across every ready provider; ~Nx cost)"
          checked={value.consensus}
          onToggle={(v) => set({ consensus: v })}
          disabled={!value.structured}
          hint={value.structured ? undefined : "Needs Structured"}
        />
        <Check
          id={`${idPrefix}-batch`}
          label="Messages Batch per watchlist ticker (50% cheaper, async)"
          checked={value.use_batch}
          onToggle={(v) => set({ use_batch: v })}
          disabled={!isClaude}
          hint={isClaude ? undefined : "Claude only — Messages Batches"}
        />
      </div>

      {/* Investigate spends real money per fire, so it ships with its cost note
          rather than as a bare checkbox. */}
      <InvestigateToggle
        idPrefix={idPrefix}
        checked={value.investigate}
        disabled={value.structured}
        onChange={(investigate) => set({ investigate })}
        note={value.structured ? "Plain fires only — structured fires ignore it." : undefined}
      />

      <p data-testid={`${idPrefix}-effective-target`} className="text-[12px] text-ink-300">
        {`Runs on ${providerLabel(eff.provider)} · ${eff.model} (${eff.qualifier})`}
      </p>
    </fieldset>
  );
}
