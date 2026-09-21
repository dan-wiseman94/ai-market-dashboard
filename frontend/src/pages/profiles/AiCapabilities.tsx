import type { ReactNode } from "react";
import { providerLabel } from "@/api/ai";
import CapabilityHint from "@/components/ai/CapabilityHint";
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";
import { MemoryPanel } from "./MemoryPanel";
import { EFFORT_OPTIONS, type Draft } from "./types";

function FeatureToggle({
  label, checked, disabled, onChange, hint,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
  hint?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-1.5">
      <div className="flex items-center gap-3">
        <Toggle checked={checked} onChange={onChange} label={label} disabled={disabled} />
        <span className={`text-[13px] ${disabled ? "text-ink-400" : "text-ink-200"}`}>{label}</span>
      </div>
      {hint}
    </div>
  );
}

/**
 * The warning a Claude-only switch earns when it is left ON under another
 * provider — an older profile later pointed at OpenAI or local. The switch
 * stays operable in that state so it can be turned OFF; every run it survives
 * writes a capability-warning message (apps/ai/capabilities.py).
 */
function StrandedHint({ feature, provider }: { feature: string; provider: string }) {
  return (
    <span role="note" className="text-[11px] text-copper-300">
      Claude only — {providerLabel(provider)} cannot honor {feature}, so every run logs a
      capability warning. Switch it off, or put the profile back on Claude.
    </span>
  );
}

/** The hint for a Claude-only feature: louder once the flag is stranded on another provider. */
function claudeOnlyHint(
  feature: "thinking" | "memory",
  label: string,
  provider: string,
  on: boolean,
): ReactNode {
  if (provider !== "claude" && on) return <StrandedHint feature={label} provider={provider} />;
  return <CapabilityHint feature={feature} provider={provider} />;
}

/**
 * The AI platform switches stored on the profile and applied to each of its runs.
 *
 * Rendered inside the form's "AI features" fieldset, which owns the legend.
 * `profileId` is null while a new profile is being created (no row yet, so no
 * memory store to inspect).
 */
export function AiCapabilities({
  draft, setDraft, profileId = null,
}: {
  draft: Draft;
  setDraft: (next: Draft) => void;
  profileId?: number | null;
}) {
  const { data: configs } = useProviderConfigs();
  const provider = draft.default_provider;
  const isClaude = provider === "claude";
  const supportsTools = configs?.find((c) => c.provider === provider)?.supports_tools;

  return (
    <>
      <FeatureToggle
        label="Enable tools"
        checked={draft.enable_tools}
        onChange={(v) => setDraft({ ...draft, enable_tools: v })}
        hint={<CapabilityHint feature="tools" provider={provider} supportsTools={supportsTools} />}
      />

      <FeatureToggle
        label="Extended thinking"
        checked={draft.enable_thinking}
        // Operable while it is on, so a stranded flag can still be switched off.
        disabled={!isClaude && !draft.enable_thinking}
        onChange={(v) => setDraft({ ...draft, enable_thinking: v })}
        hint={claudeOnlyHint("thinking", "extended thinking", provider, draft.enable_thinking)}
      />

      {isClaude && draft.enable_thinking && (
        <div className="pb-2 pl-12">
          <Field
            label="Thinking budget"
            hint="Tokens, billed as output. Minimum 1024. Legacy — only the older
              budget-shaped Claude models read it; the current models reject a raw budget
              and take Effort instead."
          >
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

      <div className="py-1.5">
        <Field
          label="Effort"
          hint="Trades cost against depth — higher effort spends more reasoning tokens on every
            run. It replaced the raw thinking-token budget on the current models. Claude clamps
            it down to whatever the chosen model accepts; OpenAI and local runs ignore it."
        >
          {({ id, describedBy }) => (
            <select
              id={id}
              aria-describedby={describedBy}
              value={draft.effort}
              onChange={(e) => {
                // Look the level up rather than casting — the select can only ever
                // hold one of these, and the lookup proves it to the type checker.
                const picked = EFFORT_OPTIONS.find((o) => o.value === e.target.value);
                if (picked) setDraft({ ...draft, effort: picked.value });
              }}
              className="ledger-input w-40 py-2"
            >
              {EFFORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          )}
        </Field>
      </div>

      <FeatureToggle
        label="Memory"
        checked={draft.enable_memory}
        disabled={!isClaude && !draft.enable_memory}
        onChange={(v) => setDraft({ ...draft, enable_memory: v })}
        hint={claudeOnlyHint("memory", "memory", provider, draft.enable_memory)}
      />

      {/* Shown whether or not the switch is on: turning memory off does not
          erase what earlier runs already wrote. */}
      <MemoryPanel profileId={profileId} />

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

      <FeatureToggle
        label="Active"
        checked={draft.active}
        onChange={(v) => setDraft({ ...draft, active: v })}
        hint={
          <span className="text-[11px] text-ink-400">
            Off keeps the profile but sorts it to the bottom of every profile list.
          </span>
        }
      />
    </>
  );
}
