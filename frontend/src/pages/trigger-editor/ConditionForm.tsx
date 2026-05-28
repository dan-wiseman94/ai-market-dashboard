import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import type { Condition, EvaluateResult, EventTrigger } from "@/api/triggers";
import type { TradingProfile } from "@/api/profiles";
import RuleBuilder from "@/components/triggers/RuleBuilder";

export type TriggerForm = Pick<
  EventTrigger,
  "name" | "condition" | "cooldown_seconds" | "enabled"
>;

export interface ConditionFormProps {
  form: TriggerForm;
  onFormChange: (next: TriggerForm) => void;
  profiles: TradingProfile[] | undefined;
  profileId: number | null;
  onProfileChange: (id: number) => void;
  preview: UseQueryResult<EvaluateResult, Error>;
  save: UseMutationResult<EventTrigger, Error, void>;
  onCancel: () => void;
}

function formatPreviewValues(values: EvaluateResult["values"]): string {
  return Object.entries(values)
    .filter(([k]) => !k.startsWith("_prior:"))
    .map(([k, v]) => `${k}=${v ?? "—"}`)
    .join(", ");
}

export default function ConditionForm({
  form, onFormChange, profiles, profileId, onProfileChange, preview, save, onCancel,
}: ConditionFormProps) {
  return (
    <>
      <div className="space-y-3">
        <div>
          <label className="block text-sm text-neutral-400 mb-1" htmlFor="tr-name">Name</label>
          <input
            id="tr-name"
            className="bg-neutral-800 px-3 py-2 rounded w-full"
            value={form.name}
            onChange={(e) => onFormChange({ ...form, name: e.target.value })}
          />
        </div>

        <div className="flex gap-4">
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Profile</label>
            <select
              className="bg-neutral-800 px-3 py-2 rounded"
              value={profileId ?? ""}
              onChange={(e) => onProfileChange(Number(e.target.value))}
            >
              {profiles?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Cooldown (sec)</label>
            <input
              type="number"
              className="bg-neutral-800 px-3 py-2 rounded w-24"
              value={form.cooldown_seconds}
              onChange={(e) => onFormChange({ ...form, cooldown_seconds: Number(e.target.value) })}
            />
          </div>
          <label className="flex items-center gap-2 mt-7">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => onFormChange({ ...form, enabled: e.target.checked })}
            />
            Enabled
          </label>
        </div>
      </div>

      <RuleBuilder
        value={form.condition}
        onChange={(c: Condition) => onFormChange({ ...form, condition: c })}
      />

      <div className="border-t border-neutral-800 pt-4 text-sm">
        <div className="text-neutral-400 mb-1">Preview — would currently fire?</div>
        {preview.isLoading && <div>Evaluating…</div>}
        {preview.isError && <div className="text-rose-700 dark:text-rose-400">Invalid condition</div>}
        {preview.data && (
          <div>
            <span className={preview.data.matched ? "text-emerald-700 dark:text-emerald-400" : "text-neutral-400"}>
              {preview.data.matched ? "YES" : "NO"}
            </span>
            <span className="ml-2 text-neutral-500">
              {formatPreviewValues(preview.data.values)}
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
          onClick={() => save.mutate()}
          disabled={save.isPending || !form.name || !profileId}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          className="bg-neutral-800 px-4 py-2 rounded"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </>
  );
}
