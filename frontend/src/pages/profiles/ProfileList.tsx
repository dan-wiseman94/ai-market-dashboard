import type { TradingProfile } from "@/api/profiles";
import { useDeleteProfile } from "@/hooks/useProfiles";

export function ProfileList({
  profiles,
  onEdit,
}: {
  profiles: TradingProfile[];
  onEdit: (p: TradingProfile) => void;
}) {
  const del = useDeleteProfile();

  return (
    <ul className="space-y-2">
      {profiles.map((p) => (
        <li key={p.id} data-testid={`profile-row-${p.name}`} className="p-3 border border-slate-800 rounded">
          <div className="flex justify-between items-start">
            <div>
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-slate-400">{p.default_model} · {p.default_includes.join(", ")}</div>
            </div>
            <div className="flex gap-2 text-sm">
              <button onClick={() => onEdit(p)} className="text-slate-300 hover:underline">Edit</button>
              <button onClick={() => del.mutate(p.id)} className="text-rose-700 dark:text-rose-400 hover:underline">Delete</button>
            </div>
          </div>
          <div className="text-xs text-slate-500 mt-2 whitespace-pre-line">{p.style}</div>
        </li>
      ))}
    </ul>
  );
}
