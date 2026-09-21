import { useState } from "react";
import { Link } from "react-router-dom";
import AiAttribution from "@/components/ai/AiAttribution";
import ModeBadges from "@/components/ai/ModeBadges";
import type { CreateScheduleBody, ObserverSchedule } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";
import { useCatalog } from "@/hooks/useCatalog";
import { useProviderConfigs } from "@/hooks/useProviderConfigs";
import { explainCron } from "@/lib/cronPreview";
import { effectiveTarget } from "./ScheduleAiFields";
import ScheduleForm from "./ScheduleForm";
import ScheduleSectionsEditor from "./ScheduleSectionsEditor";
import { useScheduleForm } from "./useScheduleForm";

/** A row's AI mode at a glance: the opt-in flags, and the target the fire resolves to.
 * Tolerates a row fetched before a field existed — the page renders list payloads
 * from several API versions. */
function RowMode({
  schedule: s, profile,
}: {
  schedule: ObserverSchedule;
  profile: TradingProfile | undefined;
}) {
  const { defaultFor } = useCatalog();
  const { data: configs } = useProviderConfigs();
  const resolvedProvider = s.override_provider || profile?.default_provider || "claude";
  const configModel = configs?.find((c) => c.provider === resolvedProvider)?.default_model ?? "";
  const eff = effectiveTarget(s, profile, defaultFor, configModel);
  return (
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
  );
}

function RowActions({
  schedule: s, editOpen, sectionsOpen, onToggle, onRun, onDelete, onToggleEdit, onToggleSections,
}: {
  schedule: ObserverSchedule;
  editOpen: boolean;
  sectionsOpen: boolean;
  onToggle: (id: number, enabled: boolean) => void;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
  onToggleEdit: () => void;
  onToggleSections: () => void;
}) {
  return (
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
        onClick={onToggleEdit}
        aria-expanded={editOpen}
        aria-label={`edit ${s.name}`}
        className="ledger-ghost"
      >
        {editOpen ? "Close editor" : "Edit"}
      </button>
      <button
        type="button"
        onClick={onToggleSections}
        aria-expanded={sectionsOpen}
        className="ledger-ghost"
      >
        {sectionsOpen ? "Hide sections" : "Sections"}
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
  );
}

/** The edit path. Mounted on open so the form seeds from the saved row, and
 * unmounted on close so a cancelled edit leaves nothing behind. */
function ScheduleEditPanel({
  schedule, profiles, isPending, onSave, onCancel,
}: {
  schedule: ObserverSchedule;
  profiles: TradingProfile[] | undefined;
  isPending: boolean;
  onSave: (id: number, body: CreateScheduleBody, onSuccess: () => void) => void;
  onCancel: () => void;
}) {
  const form = useScheduleForm(schedule);
  return (
    <div className="border-t border-rule pt-2">
      <ScheduleForm
        idPrefix={`sched-${schedule.id}`}
        profiles={profiles}
        isPending={isPending}
        form={form}
        submitLabel="Save schedule"
        pendingLabel="Saving…"
        onCancel={onCancel}
        onSubmit={(e) => {
          e.preventDefault();
          if (!form.profileId) return;
          // Close on success only: a rejected edit (foreign model, batch off Claude)
          // would otherwise discard everything the user just changed.
          onSave(schedule.id, form.payload(), onCancel);
        }}
      />
    </div>
  );
}

export default function ScheduleRow({
  schedule, profileName, profileFor, profiles, isSaving,
  onToggle, onRun, onDelete, onSaveSections, onSave,
}: {
  schedule: ObserverSchedule;
  profileName: (id: number) => string;
  profileFor: (id: number) => TradingProfile | undefined;
  profiles: TradingProfile[] | undefined;
  isSaving: boolean;
  onToggle: (id: number, enabled: boolean) => void;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
  onSaveSections: (id: number, includes: string[]) => void;
  onSave: (id: number, body: CreateScheduleBody, onSuccess: () => void) => void;
}) {
  const s = schedule;
  const [showSections, setShowSections] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const profile = profileFor(s.profile);

  return (
    <li data-testid={`schedule-row-${s.id}`} className="ledger-surface space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-ink-100">{s.name}</div>
          <div className="text-xs text-ink-500">
            {profileName(s.profile)} — {s.cron_display} ({explainCron(s.cron_display)})
          </div>
          <RowMode schedule={s} profile={profile} />
          {s.last_fired_at && (
            <div className="mt-1 text-xs text-ink-500">
              Last fired {new Date(s.last_fired_at).toLocaleString()}
            </div>
          )}
          {/* Per-profile: every profile has its own observer thread, and a fixed
              link would strand every timeline but one. */}
          <Link
            to={`/threads/observer/${s.profile}`}
            className="text-xs text-ink-400 hover:text-copper-300"
          >
            Timeline →
          </Link>
        </div>
        <RowActions
          schedule={s}
          editOpen={showEdit}
          sectionsOpen={showSections}
          onToggle={onToggle}
          onRun={onRun}
          onDelete={onDelete}
          onToggleEdit={() => setShowEdit((v) => !v)}
          onToggleSections={() => setShowSections((v) => !v)}
        />
      </div>

      {showEdit && (
        <ScheduleEditPanel
          schedule={s}
          profiles={profiles}
          isPending={isSaving}
          onSave={onSave}
          onCancel={() => setShowEdit(false)}
        />
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
