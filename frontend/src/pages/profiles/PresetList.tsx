import type { AgentPreset } from "@/api/presets";
import { useDeletePreset } from "@/hooks/useAgentPresets";

export function PresetList({
  presets,
  onEdit,
}: {
  presets: AgentPreset[];
  onEdit: (p: AgentPreset) => void;
}) {
  const deletePreset = useDeletePreset();

  return (
    <ul className="space-y-2">
      {presets.map((p) => (
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
              <div className="text-xs text-slate-500 mt-1 line-clamp-2">{p.objective_template}</div>
            </div>
            <div className="flex gap-2 text-sm shrink-0">
              <button
                onClick={() => onEdit(p)}
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
  );
}
