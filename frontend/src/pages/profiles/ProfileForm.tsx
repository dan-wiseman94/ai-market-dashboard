import ModelSelect from "@/components/settings/ModelSelect";
import { useAiModels } from "@/hooks/useAiModels";
import { SECTION_OPTIONS } from "./types";
import type { useProfileForm } from "./useProfileForm";

export function ProfileForm({ form }: { form: ReturnType<typeof useProfileForm> }) {
  const { editing, draft, setDraft, submit, toggleSection, reset } = form;
  const { data: aiModels } = useAiModels();

  return (
    <form onSubmit={submit} className="space-y-3 p-4 border border-slate-800 rounded">
      <input
        value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        placeholder="Profile name" required
        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      />
      <textarea
        value={draft.style} onChange={(e) => setDraft({ ...draft, style: e.target.value })}
        placeholder="Trading style (used as system prompt)" rows={5}
        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
      />
      <div>
        <div className="text-xs text-slate-500 mb-1">Default sections</div>
        <div className="flex flex-wrap gap-2">
          {SECTION_OPTIONS.map((sec) => (
            <label key={sec} className="flex items-center gap-1 text-sm">
              <input
                type="checkbox" checked={draft.default_includes.includes(sec)}
                onChange={() => toggleSection(sec)}
              />
              {sec}
            </label>
          ))}
        </div>
      </div>
      <div className="flex gap-2 items-start">
        <select
          aria-label="Default provider"
          value={draft.default_provider}
          onChange={(e) => {
            const provider = e.target.value;
            const firstModel =
              aiModels?.models?.find((m) => m.provider === provider)?.id ?? "";
            setDraft({ ...draft, default_provider: provider, default_model: firstModel });
          }}
          className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        >
          <option value="claude">Claude</option>
          <option value="openai">OpenAI</option>
          <option value="local">Local</option>
        </select>
        <div className="flex-1">
          <ModelSelect
            provider={draft.default_provider}
            value={draft.default_model}
            onChange={(model) => setDraft({ ...draft, default_model: model })}
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">
          {editing ? "Save" : "Create"}
        </button>
        {editing && (
          <button type="button" onClick={reset}
                  className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600">Cancel</button>
        )}
      </div>
    </form>
  );
}
