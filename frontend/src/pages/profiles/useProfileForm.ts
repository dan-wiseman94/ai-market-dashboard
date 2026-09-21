import { useState } from "react";
import type { TradingProfile } from "@/api/profiles";
import { useCreateProfile, useUpdateProfile } from "@/hooks/useProfiles";
import { BLANK_DRAFT, type Draft, toggleInArray } from "./types";

export function useProfileForm() {
  const create = useCreateProfile();
  const update = useUpdateProfile();
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
      enable_tools: p.enable_tools,
      enable_thinking: p.enable_thinking,
      thinking_budget: p.thinking_budget,
      effort: p.effort,
      enable_memory: p.enable_memory,
      enable_coach: p.enable_coach,
      active: p.active,
    });
  };

  /**
   * Switch provider, re-seeding the model and dropping the Claude-only flags.
   * Extended thinking and memory are honored by Claude alone
   * (apps/ai/capabilities.py); leaving them on for OpenAI/local writes a
   * capability-warning message into every single run instead of doing nothing.
   */
  const setProvider = (provider: string, model: string) =>
    setDraft((d) => ({
      ...d,
      default_provider: provider,
      default_model: model,
      enable_thinking: provider === "claude" ? d.enable_thinking : false,
      enable_memory: provider === "claude" ? d.enable_memory : false,
    }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editing) {
      update.mutate({ id: editing.id, body: draft }, { onSuccess: reset });
    } else {
      create.mutate(draft, { onSuccess: () => setDraft(BLANK_DRAFT) });
    }
  };

  const toggleSection = (sec: string) =>
    setDraft((d) => ({ ...d, default_includes: toggleInArray(d.default_includes, sec) }));

  return { editing, draft, setDraft, setProvider, submit, toggleSection, startEdit, reset };
}
