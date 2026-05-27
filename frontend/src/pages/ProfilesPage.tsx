import { useState } from "react";
import type { TradingProfile } from "@/api/profiles";
import {
  useCreateProfile, useDeleteProfile, useProfiles, useUpdateProfile,
} from "@/hooks/useProfiles";
import type { AgentPreset } from "@/api/presets";
import {
  useAgentPresets, useCreatePreset, useDeletePreset, useUpdatePreset,
} from "@/hooks/useAgentPresets";
import ModelSelect from "@/components/settings/ModelSelect";
import { useAiModels } from "@/hooks/useAiModels";

const SECTION_OPTIONS = ["quotes", "ohlc", "positions", "breadth", "notes"] as const;
const PRESET_SECTION_OPTIONS = ["quotes", "positions", "breadth", "ohlc", "news", "chain", "image"] as const;

type PresetDraft = {
  name: string;
  description: string;
  objective_template: string;
  default_includes: string[];
  structured: boolean;
  active: boolean;
};

const BLANK_PRESET_DRAFT: PresetDraft = {
  name: "",
  description: "",
  objective_template: "",
  default_includes: ["quotes", "positions", "breadth"],
  structured: false,
  active: true,
};

type Draft = {
  name: string;
  style: string;
  default_includes: string[];
  default_provider: string;
  default_model: string;
};

const BLANK_DRAFT: Draft = {
  name: "", style: "", default_includes: ["quotes", "positions", "breadth"],
  default_provider: "claude", default_model: "claude-sonnet-4-6",
};

export default function ProfilesPage() {
  const { data } = useProfiles();
  const create = useCreateProfile();
  const update = useUpdateProfile();
  const del = useDeleteProfile();
  const { data: aiModels } = useAiModels();
  const [editing, setEditing] = useState<TradingProfile | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK_DRAFT);

  // Preset management state
  const { data: presets } = useAgentPresets();
  const createPreset = useCreatePreset();
  const updatePreset = useUpdatePreset();
  const deletePreset = useDeletePreset();
  const [editingPreset, setEditingPreset] = useState<AgentPreset | null>(null);
  const [presetDraft, setPresetDraft] = useState<PresetDraft>(BLANK_PRESET_DRAFT);
  const [showPresetForm, setShowPresetForm] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editing) {
      update.mutate({ id: editing.id, body: draft }, {
        onSuccess: () => { setEditing(null); setDraft(BLANK_DRAFT); },
      });
    } else {
      create.mutate(draft, { onSuccess: () => setDraft(BLANK_DRAFT) });
    }
  };

  const toggleSection = (sec: string) => {
    setDraft((d) => ({
      ...d,
      default_includes: d.default_includes.includes(sec)
        ? d.default_includes.filter((s) => s !== sec)
        : [...d.default_includes, sec],
    }));
  };

  const submitPreset = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingPreset) {
      updatePreset.mutate({ id: editingPreset.id, body: presetDraft }, {
        onSuccess: () => { setEditingPreset(null); setPresetDraft(BLANK_PRESET_DRAFT); setShowPresetForm(false); },
      });
    } else {
      createPreset.mutate(presetDraft, { onSuccess: () => { setPresetDraft(BLANK_PRESET_DRAFT); setShowPresetForm(false); } });
    }
  };

  const togglePresetSection = (sec: string) => {
    setPresetDraft((d) => ({
      ...d,
      default_includes: d.default_includes.includes(sec)
        ? d.default_includes.filter((s) => s !== sec)
        : [...d.default_includes, sec],
    }));
  };

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">Trading profiles</h1>

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
            <button type="button" onClick={() => { setEditing(null); setDraft(BLANK_DRAFT); }}
                    className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600">Cancel</button>
          )}
        </div>
      </form>

      <ul className="space-y-2">
        {(data ?? []).map((p) => (
          <li key={p.id} data-testid={`profile-row-${p.name}`} className="p-3 border border-slate-800 rounded">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-slate-400">{p.default_model} · {p.default_includes.join(", ")}</div>
              </div>
              <div className="flex gap-2 text-sm">
                <button onClick={() => { setEditing(p); setDraft({
                  name: p.name, style: p.style, default_includes: p.default_includes,
                  default_provider: p.default_provider, default_model: p.default_model,
                }); }} className="text-slate-300 hover:underline">Edit</button>
                <button onClick={() => del.mutate(p.id)} className="text-rose-700 dark:text-rose-400 hover:underline">Delete</button>
              </div>
            </div>
            <div className="text-xs text-slate-500 mt-2 whitespace-pre-line">{p.style}</div>
          </li>
        ))}
      </ul>

      {/* ---- Agent presets ---- */}
      <div className="flex items-center justify-between pt-2">
        <h2 className="text-xl font-semibold">Agent presets</h2>
        {!showPresetForm && !editingPreset && (
          <button
            type="button"
            onClick={() => setShowPresetForm(true)}
            className="px-3 py-1.5 text-sm rounded bg-slate-800 hover:bg-slate-700"
          >New preset</button>
        )}
      </div>

      {(showPresetForm || editingPreset) && (
      <form data-testid="preset-form" onSubmit={submitPreset} className="space-y-3 p-4 border border-slate-800 rounded">
        <input
          value={presetDraft.name}
          onChange={(e) => setPresetDraft({ ...presetDraft, name: e.target.value })}
          placeholder="Preset name" required
          className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <textarea
          value={presetDraft.description}
          onChange={(e) => setPresetDraft({ ...presetDraft, description: e.target.value })}
          placeholder="Description (optional)" rows={2}
          className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <textarea
          value={presetDraft.objective_template}
          onChange={(e) => setPresetDraft({ ...presetDraft, objective_template: e.target.value })}
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
                  checked={presetDraft.default_includes.includes(sec)}
                  onChange={() => togglePresetSection(sec)}
                />
                {sec}
              </label>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox" checked={presetDraft.structured}
              onChange={(e) => setPresetDraft({ ...presetDraft, structured: e.target.checked })}
            />
            Structured output
          </label>
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox" checked={presetDraft.active}
              onChange={(e) => setPresetDraft({ ...presetDraft, active: e.target.checked })}
            />
            Active
          </label>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">
            {editingPreset ? "Save preset" : "Create preset"}
          </button>
          {(editingPreset || showPresetForm) && (
            <button
              type="button"
              onClick={() => { setEditingPreset(null); setPresetDraft(BLANK_PRESET_DRAFT); setShowPresetForm(false); }}
              className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600"
            >Cancel</button>
          )}
        </div>
      </form>
      )}

      <ul className="space-y-2">
        {(presets ?? []).map((p) => (
          <li key={p.id} data-testid={`preset-row-${p.name}`} className="p-3 border border-slate-800 rounded">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium flex items-center gap-2">
                  {p.name}
                  {p.builtin && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-normal">
                      builtin
                    </span>
                  )}
                  {!p.active && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 font-normal">
                      inactive
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400">{p.default_includes.join(", ")}</div>
                <div className="text-xs text-slate-500 mt-1 line-clamp-2">{p.objective_template}</div>
              </div>
              <div className="flex gap-2 text-sm shrink-0">
                <button
                  onClick={() => {
                    setEditingPreset(p);
                    setPresetDraft({
                      name: p.name,
                      description: p.description,
                      objective_template: p.objective_template,
                      default_includes: p.default_includes,
                      structured: p.structured,
                      active: p.active,
                    });
                  }}
                  className="text-slate-300 hover:underline"
                >Edit</button>
                <button
                  onClick={() => deletePreset.mutate(p.id)}
                  className="text-rose-700 dark:text-rose-400 hover:underline"
                >Delete</button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
