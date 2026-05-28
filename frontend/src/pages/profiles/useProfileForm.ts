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
    });
  };

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

  return { editing, draft, setDraft, submit, toggleSection, startEdit, reset };
}
