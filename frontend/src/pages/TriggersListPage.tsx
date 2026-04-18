import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchTriggers, updateTrigger, deleteTrigger, fireTriggerNow,
  type EventTrigger,
} from "@/api/triggers";
import { describeCondition } from "@/lib/triggers/describe";

export default function TriggersListPage() {
  const qc = useQueryClient();
  const { data: triggers, isLoading } = useQuery({
    queryKey: ["triggers"],
    queryFn: fetchTriggers,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateTrigger(id, { enabled }),
    onMutate: async ({ id, enabled }) => {
      await qc.cancelQueries({ queryKey: ["triggers"] });
      const prev = qc.getQueryData<EventTrigger[]>(["triggers"]);
      qc.setQueryData<EventTrigger[]>(["triggers"], (rows) =>
        (rows ?? []).map((t) => (t.id === id ? { ...t, enabled } : t)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["triggers"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["triggers"] }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteTrigger(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["triggers"] }),
  });

  const fire = useMutation({
    mutationFn: (id: number) => fireTriggerNow(id),
  });

  if (isLoading) return <div className="p-6">Loading…</div>;

  if (!triggers?.length) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-semibold">Triggers</h1>
          <Link to="/triggers/new" className="bg-indigo-600 px-3 py-1.5 rounded text-white">New trigger</Link>
        </div>
        <p className="text-neutral-400">No triggers yet.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">Triggers</h1>
        <Link to="/triggers/new" className="bg-indigo-600 px-3 py-1.5 rounded text-white">New trigger</Link>
      </div>
      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left">
          <tr>
            <th className="py-2">Name</th>
            <th className="py-2">Condition</th>
            <th className="py-2">Last fired</th>
            <th className="py-2">Firings</th>
            <th className="py-2">Enabled</th>
            <th className="py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {triggers.map((t) => (
            <tr key={t.id} className="border-t border-neutral-800">
              <td className="py-2 font-medium">
                <Link to={`/triggers/${t.id}`} className="hover:text-indigo-400">{t.name}</Link>
              </td>
              <td className="py-2 text-neutral-400 max-w-md truncate">
                {describeCondition(t.condition)}
              </td>
              <td className="py-2 tabular-nums text-neutral-400">
                {t.last_fired_at ? new Date(t.last_fired_at).toLocaleString() : "—"}
              </td>
              <td className="py-2 tabular-nums">{t.firings_count} firings</td>
              <td className="py-2">
                <input
                  type="checkbox"
                  checked={t.enabled}
                  aria-label={`enable ${t.name}`}
                  onChange={(e) => toggle.mutate({ id: t.id, enabled: e.target.checked })}
                />
              </td>
              <td className="py-2 space-x-2">
                <button
                  className="text-amber-400 hover:text-amber-300"
                  onClick={() => {
                    if (window.confirm(`Fire "${t.name}" now? This will capture a snapshot and run the AI.`)) {
                      fire.mutate(t.id);
                    }
                  }}
                >
                  Fire now
                </button>
                <Link to={`/triggers/${t.id}`} className="text-indigo-400 hover:text-indigo-300">Edit</Link>
                <button
                  className="text-rose-400 hover:text-rose-300"
                  onClick={() => {
                    if (window.confirm(`Delete "${t.name}"? Firings history will be removed.`)) {
                      remove.mutate(t.id);
                    }
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
