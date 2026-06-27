import { useState } from "react";
import type { AgentPreset } from "@/api/presets";
import { useCreatePreset, useUpdatePreset } from "@/hooks/useAgentPresets";
import { BLANK_PRESET_DRAFT, type PresetDraft } from "./types";

export function usePresetForm() {
  const createPreset = useCreatePreset();
  const updatePreset = useUpdatePreset();
  const [editing, setEditing] = useState<AgentPreset | null>(null);
  const [draft, setDraft] = useState<PresetDraft>(BLANK_PRESET_DRAFT);
  const [showForm, setShowForm] = useState(false);

  const close = () => {
    setEditing(null);
    setDraft(BLANK_PRESET_DRAFT);
    setShowForm(false);
  };

  const startEdit = (p: AgentPreset) => {
    setEditing(p);
    setDraft({
      name: p.name,
      description: p.description,
      objective_template: p.objective_template,
      structured: p.structured,
      active: p.active,
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editing) {
      updatePreset.mutate({ id: editing.id, body: draft }, { onSuccess: close });
    } else {
      createPreset.mutate(draft, {
        onSuccess: () => {
          setDraft(BLANK_PRESET_DRAFT);
          setShowForm(false);
        },
      });
    }
  };

  return { editing, draft, setDraft, showForm, setShowForm, submit, startEdit, close };
}
