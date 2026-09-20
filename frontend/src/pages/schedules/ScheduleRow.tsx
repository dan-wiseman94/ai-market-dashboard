import { useState } from "react";
import AiAttribution from "@/components/ai/AiAttribution";
import ModeBadges from "@/components/ai/ModeBadges";
import type { ObserverSchedule } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { useCatalog } from "@/hooks/useCatalog";
import { explainCron } from "@/lib/cronPreview";
import ScheduleAiFields, {
  aiFieldsFrom, effectiveTarget, type AiFieldsValue,
} from "./ScheduleAiFields";
import ScheduleSectionsEditor from "./ScheduleSectionsEditor";

export default function ScheduleRow({
  schedule, profileName, profileFor, onToggle, onRun, onDelete, onSaveSections, onSaveAi,
}: {
  schedule: ObserverSchedule;
  profileName: (id: number) => string;
  profileFor: (id: number) => TradingProfile | undefined;
  onToggle: (id: number, enabled: boolean) => void;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
  onSaveSections: (id: number, includes: string[]) => void;
  onSaveAi: (id: number, value: AiFieldsValue) => void;
}) {
  const s = schedule;
  const [showSections, setShowSections] = useState(false);
  const [ai, setAi] = useState<AiFieldsValue | null>(null);
  const { defaultFor } = useCatalog();
  const profile = profileFor(s.profile);
  const eff = effectiveTarget(s, profile, defaultFor);

  return (
    <li data-testid={`schedule-row-${s.id}`} className="ledger-surface space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-ink-100">{s.name}</div>
          <div className="text-xs text-ink-500">
            {profileName(s.profile)} — {s.cron_display} ({explainCron(s.cron_display)})
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <ModeBadges
              mode={s.mode ?? "full"}
              structured={s.structured ?? false}
              consensus={s.consensus ?? false}
              use_batch={s.use_batch ?? false}
              investigate={s.investigate ?? false}
            />
            <AiAttribution
              provider={eff.provider}
              model={eff.model}
              qualifier={s.override_provider ? "override" : "profile"}
            />
          </div>
          {s.last_fired_at && (
            <div className="mt-1 text-xs text-ink-500">
              Last fired {new Date(s.last_fired_at).toLocaleString()}
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-ink-300">
            <input
              type="checkbox"
              checked={s.enabled}
              onChange={(e) => onToggle(s.id, e.target.checked)}
            />
            enabled
          </label>
          <button type="button" onClick={() => onRun(s.id)} className="ledger-cta">Run now</button>
          <button
            type="button"
            onClick={() => setAi((v) => (v === null ? aiFieldsFrom(s) : null))}
            className="ledger-ghost"
          >
            {ai === null ? "AI" : "Hide AI"}
          </button>
          <button
            type="button"
            onClick={() => setShowSections((v) => !v)}
            className="ledger-ghost"
          >
            {showSections ? "Hide sections" : "Sections"}
          </button>
          <button
            type="button"
            onClick={() => onDelete(s.id)}
            aria-label={`delete ${s.name}`}
            className="ledger-ghost text-loss"
          >
            Delete
          </button>
        </div>
      </div>

      {ai !== null && (
        <div className="space-y-2 border-t border-rule pt-2">
          <ScheduleAiFields
            value={ai}
            onChange={setAi}
            profile={profile}
            idPrefix={`sched-${s.id}`}
          />
          <button
            type="button"
            onClick={() => { onSaveAi(s.id, ai); setAi(null); }}
            className="ledger-cta"
          >
            Save AI settings
          </button>
        </div>
      )}

      {showSections && (
        <ScheduleSectionsEditor
          schedule={s}
          onSave={(includes) => { onSaveSections(s.id, includes); setShowSections(false); }}
        />
      )}
    </li>
  );
}
