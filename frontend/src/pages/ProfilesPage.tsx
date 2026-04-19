import { useState } from "react";
import type { TradingProfile } from "@/api/profiles";
import {
  useCreateProfile, useDeleteProfile, useProfiles, useUpdateProfile,
} from "@/hooks/useProfiles";

const SECTION_OPTIONS = ["quotes", "ohlc", "positions", "breadth", "notes"] as const;

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
  const [editing, setEditing] = useState<TradingProfile | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK_DRAFT);

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
        <div className="flex gap-2">
          <input
            value={draft.default_model}
            onChange={(e) => setDraft({ ...draft, default_model: e.target.value })}
            placeholder="claude-sonnet-4-6"
            className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
          <select
            value={draft.default_provider}
            onChange={(e) => setDraft({ ...draft, default_provider: e.target.value })}
            className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="claude">Claude</option>
            <option value="openai">OpenAI</option>
            <option value="local">Local</option>
          </select>
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
                <button onClick={() => del.mutate(p.id)} className="text-rose-400 hover:underline">Delete</button>
              </div>
            </div>
            <div className="text-xs text-slate-500 mt-2 whitespace-pre-line">{p.style}</div>
          </li>
        ))}
      </ul>
    </main>
  );
}
