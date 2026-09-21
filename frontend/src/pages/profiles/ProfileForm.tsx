import AiTargetPicker from "@/components/ai/AiTargetPicker";
import Field from "@/components/settings/Field";
import { SECTION_LABELS, VIX_LABEL } from "@/lib/snapshotSections";
import { AiCapabilities } from "./AiCapabilities";
import { SECTION_OPTIONS } from "./types";
import type { useProfileForm } from "./useProfileForm";

function Legend({ children }: { children: string }) {
  return (
    <legend className="mb-2 font-mono text-[10px] uppercase tracking-loose2 text-copper-400">
      {children}
    </legend>
  );
}

export function ProfileForm({ form }: { form: ReturnType<typeof useProfileForm> }) {
  const { editing, draft, setDraft, setTarget, submit, toggleSection, reset } = form;

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
          onChange={setTarget}
          providerLabel="Default provider"
          modelLabel="Default model"
          facts
        />
      </fieldset>

      <fieldset className="border-t border-rule-soft pt-4">
        <Legend>AI features</Legend>
        <AiCapabilities draft={draft} setDraft={setDraft} profileId={editing?.id ?? null} />
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
