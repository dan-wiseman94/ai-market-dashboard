import AiAttribution from "@/components/ai/AiAttribution";
import type { TradingProfile } from "@/api/profiles";
import { useDeleteProfile, useUpdateProfile } from "@/hooks/useProfiles";
import { useToast } from "@/hooks/useToast";

/** The opt-in AI features this profile turns on, as pills. */
function FeaturePills({ p }: { p: TradingProfile }) {
  const on = [
    p.enable_tools && "tools",
    p.enable_thinking && "thinking",
    p.enable_memory && "memory",
    p.enable_coach && "coach",
  ].filter(Boolean) as string[];
  if (on.length === 0) return null;
  return (
    <>
      {on.map((f) => (
        <span key={f} className="ledger-pill" data-tone="copper">{f}</span>
      ))}
    </>
  );
}

export function ProfileList({
  profiles,
  onEdit,
}: {
  profiles: TradingProfile[];
  onEdit: (p: TradingProfile) => void;
}) {
  const del = useDeleteProfile();
  const update = useUpdateProfile();
  const { push } = useToast();

  const setActive = (p: TradingProfile) =>
    update.mutate(
      { id: p.id, body: { active: !p.active } },
      { onError: (e) => push({ kind: "error", text: (e as Error).message }) },
    );

  return (
    <ul className="space-y-2">
      {profiles.map((p) => (
        <li key={p.id} data-testid={`profile-row-${p.name}`} className="ledger-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink-100">{p.name}</span>
                {!p.active && <span className="ledger-pill" data-tone="loss">Inactive</span>}
                <AiAttribution provider={p.default_provider} model={p.default_model} />
                <FeaturePills p={p} />
              </div>
              <div className="mt-1 text-[11px] text-ink-400">
                {p.default_includes.join(", ")}
              </div>
            </div>
            <div className="flex shrink-0 gap-2 text-sm">
              <button type="button" onClick={() => onEdit(p)} className="ledger-ghost">Edit</button>
              <button
                type="button"
                onClick={() => setActive(p)}
                title="Active profiles sort first"
                className="ledger-ghost"
              >
                {p.active ? "Deactivate" : "Activate"}
              </button>
              <button
                type="button"
                onClick={() => del.mutate(p.id)}
                className="ledger-ghost text-loss"
              >
                Delete
              </button>
            </div>
          </div>
          <div className="mt-2 whitespace-pre-line text-[12px] text-ink-400">{p.style}</div>
        </li>
      ))}
    </ul>
  );
}
