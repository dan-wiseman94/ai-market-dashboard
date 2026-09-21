import { useId } from "react";
import type { Effort } from "@/api/profiles";
import { MemoryPanel } from "./MemoryPanel";
import { EFFORT_OPTIONS, type Draft } from "./types";

const PROVIDER_LABELS: Record<string, string> = {
  claude: "Claude",
  openai: "OpenAI",
  local: "Local",
};

function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

/** A labelled checkbox whose help text is always wired up via aria-describedby. */
function CheckRow({
  label, hint, checked, disabled, onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className="flex items-center gap-2 text-sm">
        <input
          id={id} type="checkbox" checked={checked} disabled={disabled}
          aria-describedby={hintId}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className={disabled ? "text-slate-500" : undefined}>{label}</span>
      </label>
      <p id={hintId} className="pl-6 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

/**
 * The reason a Claude-only switch is unavailable. When the stored profile has it
 * on anyway (an older profile later pointed at OpenAI/local) the control stays
 * operable so it can be switched OFF — every run it survives writes a
 * capability-warning message (apps/ai/capabilities.py).
 */
function claudeOnlyHint(feature: string, provider: string, on: boolean): string {
  const name = providerLabel(provider);
  return on
    ? `Claude only — ${name} cannot honor ${feature}, so every run logs a capability warning. Switch it off, or put the profile back on Claude.`
    : `Claude only — ${name} runs ignore ${feature}.`;
}

function ThinkingBudgetField({
  value, onChange,
}: {
  value: number;
  onChange: (next: number) => void;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="space-y-0.5 pl-6">
      <label htmlFor={id} className="block text-xs text-slate-400">
        Thinking budget (tokens)
      </label>
      <input
        id={id} type="number" min={1024} step={1} value={value}
        aria-describedby={hintId}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-40 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 tabular-nums"
      />
      <p id={hintId} className="text-xs text-slate-500">
        Legacy — only the older budget-shaped Claude models (Haiku 4.5) read it. The current
        models reject a raw budget and take Effort instead, so it is ignored there.
      </p>
    </div>
  );
}

function EffortField({
  value, onChange,
}: {
  value: Effort;
  onChange: (next: Effort) => void;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className="block text-sm">Effort</label>
      <select
        id={id} value={value} aria-describedby={hintId}
        onChange={(e) => {
          // Look the level up rather than casting — the select can only ever
          // hold one of these, and the lookup proves it to the type checker.
          const picked = EFFORT_OPTIONS.find((o) => o.value === e.target.value);
          if (picked) onChange(picked.value);
        }}
        className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      >
        {EFFORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <p id={hintId} className="text-xs text-slate-500">
        Trades cost against depth — higher effort spends more reasoning tokens on every run.
        It replaced the raw thinking-token budget on the current models. Claude clamps it down
        to whatever the chosen model accepts; OpenAI and local runs ignore it.
      </p>
    </div>
  );
}

/**
 * The AI platform switches stored on the profile and applied to each of its runs.
 *
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
  const isClaude = draft.default_provider === "claude";

  return (
    <fieldset className="space-y-3 rounded border border-slate-800 p-3">
      <legend className="px-1 text-xs uppercase tracking-wide text-slate-400">
        AI capabilities
      </legend>

      <CheckRow
        label="Tools"
        checked={draft.enable_tools}
        onChange={(v) => setDraft({ ...draft, enable_tools: v })}
        hint={
          isClaude
            ? "Exposes get_quote, fetch_ohlc, search_news, get_option_chain and compute_indicator to the model."
            : `Exposes the read-only market tools. ${providerLabel(draft.default_provider)} also needs "Tool use" enabled on its provider card in Settings → Providers, or this stays inert.`
        }
      />

      <CheckRow
        label="Extended thinking"
        checked={draft.enable_thinking}
        disabled={!isClaude && !draft.enable_thinking}
        onChange={(v) => setDraft({ ...draft, enable_thinking: v })}
        hint={
          isClaude
            ? "The model reasons before it answers. Those tokens are billed as output."
            : claudeOnlyHint("extended thinking", draft.default_provider, draft.enable_thinking)
        }
      />

      {isClaude && draft.enable_thinking && (
        <ThinkingBudgetField
          value={draft.thinking_budget}
          onChange={(v) => setDraft({ ...draft, thinking_budget: v })}
        />
      )}

      <EffortField
        value={draft.effort}
        onChange={(v) => setDraft({ ...draft, effort: v })}
      />

      <CheckRow
        label="Memory"
        checked={draft.enable_memory}
        disabled={!isClaude && !draft.enable_memory}
        onChange={(v) => setDraft({ ...draft, enable_memory: v })}
        hint={
          isClaude
            ? "Gives the model a store scoped to this profile alone, kept between runs. It writes it itself, out of turns that carry untrusted data — read it below."
            : claudeOnlyHint("memory", draft.default_provider, draft.enable_memory)
        }
      />

      {/* Shown whether or not the switch is on: turning memory off does not
          erase what earlier runs already wrote. */}
      <MemoryPanel profileId={profileId} />

      <CheckRow
        label="Decision Coach"
        checked={draft.enable_coach}
        onChange={(v) => setDraft({ ...draft, enable_coach: v })}
        hint="Injects prior theses, the diff against the last snapshot, your per-ticker track record and distilled lessons. Off leaves the system prompt as just the style text."
      />

      <CheckRow
        label="Active"
        checked={draft.active}
        onChange={(v) => setDraft({ ...draft, active: v })}
        hint="Off keeps the profile but sorts it to the bottom of every profile list."
      />
    </fieldset>
  );
}
