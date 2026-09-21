import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useSchedules, useToggleSchedule, useDeleteSchedule,
  useRunSchedule, useCreateSchedule, useUpdateSchedule, useUpdateScheduleIncludes,
} from "@/hooks/useSchedules";
import { useProfiles } from "@/hooks/useProfiles";
import { explainCron } from "@/lib/cronPreview";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";
import ScheduleForm from "@/components/schedule/ScheduleForm";
import {
  buildSchedulePayload, emptyScheduleValues, scheduleToValues,
  type ScheduleFormValues,
} from "@/components/schedule/scheduleFormValues";
import type { ObserverSchedule } from "@/api/observer";
import type { TradingProfile } from "@/api/profiles";

function ScheduleSectionsEditor({
  schedule, onSave,
}: {
  schedule: ObserverSchedule;
  onSave: (includes: string[]) => void;
}) {
  const [includes, setIncludes] = useState<string[]>(schedule.default_includes);
  return (
    <div className="mt-2 space-y-2 pt-2 border-t border-rule">
      {includes.length === 0 && (
        <div className="text-xs text-ink-500">
          Empty — inherits the profile&apos;s default sections.
        </div>
      )}
      <SnapshotSectionPicker value={includes} onChange={setIncludes} />
      <button
        type="button"
        onClick={() => onSave(includes)}
        className="px-2 py-1 text-xs rounded bg-gain-500 hover:bg-gain-400"
      >
        Save sections
      </button>
    </div>
  );
}

/**
 * Edit an existing schedule with the same form the create path uses — the only
 * way `market_hours_only`, `mode`, `structured`, `use_batch`, `consensus`,
 * `fire_mode` and `close_offset_minutes` are reachable after create.
 */
function ScheduleEditPanel({
  schedule, profiles, onDone,
}: {
  schedule: ObserverSchedule;
  profiles: TradingProfile[] | undefined;
  onDone: () => void;
}) {
  const update = useUpdateSchedule();
  const [values, setValues] = useState<ScheduleFormValues>(() => scheduleToValues(schedule));
  const [profileId, setProfileId] = useState<number>(schedule.profile);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({
        id: schedule.id,
        body: buildSchedulePayload(values, profileId),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the schedule.");
    }
  }

  return (
    <div className="mt-2 pt-2 border-t border-rule">
      <ScheduleForm
        idPrefix={`sched-edit-${schedule.id}`}
        values={values}
        onChange={(patch) => setValues((v) => ({ ...v, ...patch }))}
        profiles={profiles}
        profileId={profileId}
        onProfileChange={setProfileId}
        onSubmit={onSubmit}
        submitLabel="Save schedule"
        pendingLabel="Saving…"
        isPending={update.isPending}
        onCancel={onDone}
        error={error}
      />
    </div>
  );
}

function ScheduleRow({
  schedule, profiles, profileName, onToggle, onRun, onDelete, onSaveSections,
}: {
  schedule: ObserverSchedule;
  profiles: TradingProfile[] | undefined;
  profileName: (id: number) => string;
  onToggle: (id: number, enabled: boolean) => void;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
  onSaveSections: (id: number, includes: string[]) => void;
}) {
  const s = schedule;
  const [showSections, setShowSections] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  return (
    <li data-testid={`schedule-row-${s.id}`} className="p-4 rounded border border-rule bg-ink-900 space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-semibold">{s.name}</div>
          <div className="text-xs text-ink-500">
            {profileName(s.profile)} — {s.cron_display} ({explainCron(s.cron_display)})
          </div>
          {s.last_fired_at && (
            <div className="text-xs text-ink-500">
              Last fired {new Date(s.last_fired_at).toLocaleString()}
            </div>
          )}
          <Link
            to={`/threads/observer/${s.profile}`}
            className="text-xs text-ink-400 hover:text-copper-300"
          >
            Timeline →
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs flex items-center gap-1">
            <input
              type="checkbox"
              checked={s.enabled}
              onChange={(e) => onToggle(s.id, e.target.checked)}
            />
            enabled
          </label>
          <button type="button" onClick={() => onRun(s.id)}
                  className="px-2 py-1 text-xs rounded bg-gain-500 hover:bg-gain-400">Run now</button>
          <button type="button" onClick={() => setShowEdit((v) => !v)}
                  aria-expanded={showEdit}
                  aria-label={`edit ${s.name}`}
                  className="px-2 py-1 text-xs rounded bg-ink-800 hover:bg-ink-700">
            {showEdit ? "Close editor" : "Edit"}
          </button>
          <button type="button" onClick={() => setShowSections((v) => !v)}
                  aria-expanded={showSections}
                  className="px-2 py-1 text-xs rounded bg-ink-800 hover:bg-ink-700">
            {showSections ? "Hide sections" : "Sections"}
          </button>
          <button type="button" onClick={() => onDelete(s.id)}
                  aria-label={`delete ${s.name}`}
                  className="px-2 py-1 text-xs rounded bg-loss-500 hover:bg-loss-400">Delete</button>
        </div>
      </div>
      {showSections && (
        <ScheduleSectionsEditor
          schedule={s}
          onSave={(includes) => { onSaveSections(s.id, includes); setShowSections(false); }}
        />
      )}
      {showEdit && (
        <ScheduleEditPanel
          schedule={s}
          profiles={profiles}
          onDone={() => setShowEdit(false)}
        />
      )}
    </li>
  );
}

export default function SchedulesPage() {
  const { data: schedules, isLoading } = useSchedules();
  const { data: profiles } = useProfiles();
  const toggle = useToggleSchedule();
  const del = useDeleteSchedule();
  const run = useRunSchedule();
  const create = useCreateSchedule();
  const updateIncludes = useUpdateScheduleIncludes();

  const [showForm, setShowForm] = useState(false);
  const [values, setValues] = useState<ScheduleFormValues>(emptyScheduleValues);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  // Default to the first profile once loaded. Render-phase guarded update
  // (React's "adjust state when data changes") rather than an effect, which
  // avoids react-hooks/set-state-in-effect cascading renders.
  if (profileId === null && profiles && profiles.length > 0) {
    setProfileId(profiles[0].id);
  }

  const profileName = (id: number) =>
    profiles?.find((p) => p.id === id)?.name ?? `#${id}`;

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!profileId) return;
    setCreateError(null);
    try {
      await create.mutateAsync(buildSchedulePayload(values, profileId));
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not create the schedule.");
      return;
    }
    setValues(emptyScheduleValues());
    setShowForm(false);
  }

  if (isLoading) {
    return (
      <main className="p-6 max-w-3xl mx-auto space-y-4">
        <h1 className="text-2xl font-semibold">Observer schedules</h1>
        <SkeletonRows rows={3} />
      </main>
    );
  }

  const rows = Array.isArray(schedules) ? schedules : [];

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Observer schedules</h1>

      {rows.length === 0 && (
        <EmptyState
          title="No schedules yet"
          body="Create one to have the observer capture + analyze snapshots on a cron."
        />
      )}

      <ul className="space-y-2">
        {rows.map((s) => (
          <ScheduleRow
            key={s.id}
            schedule={s}
            profiles={profiles}
            profileName={profileName}
            onToggle={(id, en) => toggle.mutate({ id, enabled: en })}
            onRun={(id) => run.mutate(id)}
            onDelete={(id) => del.mutate(id)}
            onSaveSections={(id, includes) =>
              updateIncludes.mutate({ id, default_includes: includes })}
          />
        ))}
      </ul>

      <button
        type="button"
        onClick={() => setShowForm((v) => !v)}
        className="px-3 py-1 rounded bg-ink-700 hover:bg-ink-600"
      >{showForm ? "Cancel" : "+ New schedule"}</button>

      {showForm && (
        <ScheduleForm
          idPrefix="sched"
          values={values}
          onChange={(patch) => setValues((v) => ({ ...v, ...patch }))}
          profiles={profiles}
          profileId={profileId}
          onProfileChange={setProfileId}
          onSubmit={onCreate}
          submitLabel="Create"
          pendingLabel="Creating…"
          isPending={create.isPending}
          error={createError}
        />
      )}
    </main>
  );
}
