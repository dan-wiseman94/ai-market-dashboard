import { PRESET_SECTION_OPTIONS } from "./types";
import type { usePresetForm } from "./usePresetForm";

export function PresetForm({ form }: { form: ReturnType<typeof usePresetForm> }) {
  const { editing, draft, setDraft, submit, toggleSection, close } = form;

  return (
    <form data-testid="preset-form" onSubmit={submit} className="space-y-3 p-4 border border-slate-800 rounded">
      <input
        value={draft.name}
        onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        placeholder="Preset name" required
        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      />
      <textarea
        value={draft.description}
        onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        placeholder="Description (optional)" rows={2}
        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      />
      <textarea
        value={draft.objective_template}
        onChange={(e) => setDraft({ ...draft, objective_template: e.target.value })}
        placeholder="Objective template (filled into the composer)" rows={3} required
        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      />
      <div>
        <div className="text-xs text-slate-500 mb-1">Default sections</div>
        <div className="flex flex-wrap gap-2">
          {PRESET_SECTION_OPTIONS.map((sec) => (
            <label key={sec} className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={draft.default_includes.includes(sec)}
                onChange={() => toggleSection(sec)}
              />
              {sec}
            </label>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox" checked={draft.structured}
            onChange={(e) => setDraft({ ...draft, structured: e.target.checked })}
          />
          Structured output
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox" checked={draft.active}
            onChange={(e) => setDraft({ ...draft, active: e.target.checked })}
          />
          Active
        </label>
      </div>
      <div className="flex gap-2">
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">
          {editing ? "Save preset" : "Create preset"}
        </button>
        <button
          type="button"
          onClick={close}
          className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600"
        >Cancel</button>
      </div>
    </form>
  );
}
