import type { ReactNode } from "react";
import AiTargetPicker from "@/components/ai/AiTargetPicker";
import CapabilityHint from "@/components/ai/CapabilityHint";
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";
import { SECTION_LABELS, VIX_LABEL } from "@/lib/snapshotSections";
import { SECTION_OPTIONS } from "./types";
import type { useProfileForm } from "./useProfileForm";

function Legend({ children }: { children: string }) {
  return (
    <legend className="mb-2 font-mono text-[10px] uppercase tracking-loose2 text-copper-400">
      {children}
    </legend>
  );
}

function FeatureToggle({
  label, checked, onChange, hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-1.5">
      <div className="flex items-center gap-3">
        <Toggle checked={checked} onChange={onChange} label={label} />
        <span className="text-[13px] text-ink-200">{label}</span>
      </div>
      {hint}
    </div>
  );
}

export function ProfileForm({ form }: { form: ReturnType<typeof useProfileForm> }) {
  const { editing, draft, setDraft, submit, toggleSection, reset } = form;
  const { data: configs } = useProviderConfigs();
  const provider = draft.default_provider;
  const supportsTools = configs?.find((c) => c.provider === provider)?.supports_tools;

  return (
    <form onSubmit={submit} className="ledger-surface space-y-5 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          {({ id }) => (
            <input
              id={id}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Profile name"
              required
              className="ledger-input w-full py-2"
            />
          )}
        </Field>
        <div className="sm:col-span-2">
          <Field label="Trading style" hint="Prepended as the system prompt on every run.">
            {({ id, describedBy }) => (
              <textarea
                id={id}
                aria-describedby={describedBy}
                value={draft.style}
                onChange={(e) => setDraft({ ...draft, style: e.target.value })}
                placeholder="Trading style (used as system prompt)"
                rows={5}
                className="ledger-input w-full py-2"
              />
            )}
          </Field>
        </div>
      </div>

      <fieldset>
        <Legend>Default sections</Legend>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {SECTION_OPTIONS.map((sec) => (
            <label key={sec} className="flex items-center gap-1.5 text-[13px] text-ink-200">
              <input
                type="checkbox"
                checked={draft.default_includes.includes(sec)}
                onChange={() => toggleSection(sec)}
              />
              {SECTION_LABELS[sec]}
            </label>
          ))}
        </div>
        <div className="mt-2">
          <span data-testid="vix-always-included-chip" className="ledger-pill">
            {VIX_LABEL} — always included
          </span>
        </div>
      </fieldset>

      <fieldset>
        <Legend>Default AI target</Legend>
        <AiTargetPicker
          value={{ provider: draft.default_provider, model: draft.default_model }}
          onChange={(t) => setDraft({ ...draft, default_provider: t.provider, default_model: t.model })}
          providerLabel="Default provider"
          modelLabel="Default model"
          facts
        />
      </fieldset>

      <fieldset className="border-t border-rule-soft pt-4">
        <Legend>AI features</Legend>
        <FeatureToggle
          label="Enable tools"
          checked={draft.enable_tools}
          onChange={(v) => setDraft({ ...draft, enable_tools: v })}
          hint={<CapabilityHint feature="tools" provider={provider} supportsTools={supportsTools} />}
        />
        <FeatureToggle
          label="Extended thinking"
          checked={draft.enable_thinking}
          onChange={(v) => setDraft({ ...draft, enable_thinking: v })}
          hint={<CapabilityHint feature="thinking" provider={provider} />}
        />
        {draft.enable_thinking && (
          <div className="pb-2 pl-12">
            <Field label="Thinking budget" hint="Tokens, billed as output. Minimum 1024.">
              {({ id, describedBy }) => (
                <input
                  id={id}
                  aria-label="Thinking budget"
                  aria-describedby={describedBy}
                  inputMode="numeric"
                  value={draft.thinking_budget}
                  onChange={(e) =>
                    setDraft({ ...draft, thinking_budget: Number(e.target.value.replace(/\D/g, "")) })
                  }
                  onBlur={(e) =>
                    // Anthropic rejects a budget below 1024, and 0 silently disables
                    // thinking — clamp rather than save a value that can't work.
                    setDraft({
                      ...draft,
                      thinking_budget: Math.max(1024, Number(e.target.value.replace(/\D/g, ""))),
                    })
                  }
                  className="ledger-input w-40 py-2 tabular-nums"
                />
              )}
            </Field>
          </div>
        )}
        <FeatureToggle
          label="Memory"
          checked={draft.enable_memory}
          onChange={(v) => setDraft({ ...draft, enable_memory: v })}
          hint={<CapabilityHint feature="memory" provider={provider} />}
        />
        <FeatureToggle
          label="Decision Coach"
          checked={draft.enable_coach}
          onChange={(v) => setDraft({ ...draft, enable_coach: v })}
          hint={
            <span className="text-[11px] text-ink-400">
              Calibration, base rates and lessons in the system prompt.
            </span>
          }
        />
      </fieldset>

      <div className="flex gap-2">
        <button type="submit" className="ledger-cta">{editing ? "Save" : "Create"}</button>
        {editing && (
          <button type="button" onClick={reset} className="ledger-ghost">Cancel</button>
        )}
      </div>
    </form>
  );
}
