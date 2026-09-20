import { useState } from "react";
import type { TradingProfile } from "@/api/profiles";
import { useCreateProfile, useUpdateProfile } from "@/hooks/useProfiles";
import { useToast } from "@/hooks/useToast";
import { BLANK_DRAFT, type Draft, toggleInArray } from "./types";

export function useProfileForm() {
  const create = useCreateProfile();
  const update = useUpdateProfile();
  const { push } = useToast();
  const [editing, setEditing] = useState<TradingProfile | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK_DRAFT);

  const reset = () => {
    setEditing(null);
    setDraft(BLANK_DRAFT);
  };

  const startEdit = (p: TradingProfile) => {
    setEditing(p);
    setDraft({
      name: p.name,
      style: p.style,
      default_includes: p.default_includes,
      default_provider: p.default_provider,
      default_model: p.default_model,
      enable_tools: p.enable_tools ?? BLANK_DRAFT.enable_tools,
      enable_thinking: p.enable_thinking ?? BLANK_DRAFT.enable_thinking,
      thinking_budget: p.thinking_budget ?? BLANK_DRAFT.thinking_budget,
      enable_memory: p.enable_memory ?? BLANK_DRAFT.enable_memory,
      enable_coach: p.enable_coach ?? BLANK_DRAFT.enable_coach,
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    // The vendor guard rejects a model that belongs to another provider's catalog;
    // surface that 400 instead of leaving the form silently unchanged.
    const onError = (err: unknown) => push({ kind: "error", text: (err as Error).message });
    if (editing) {
      update.mutate({ id: editing.id, body: draft }, { onSuccess: reset, onError });
    } else {
      create.mutate(draft, { onSuccess: () => setDraft(BLANK_DRAFT), onError });
    }
  };

  const toggleSection = (sec: string) =>
    setDraft((d) => ({ ...d, default_includes: toggleInArray(d.default_includes, sec) }));

  return { editing, draft, setDraft, submit, toggleSection, startEdit, reset };
}
