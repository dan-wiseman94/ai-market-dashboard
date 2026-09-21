import { useState } from "react";
import {
  useSchedules, useToggleSchedule, useDeleteSchedule,
  useRunSchedule, useCreateSchedule, useUpdateSchedule, useUpdateScheduleIncludes,
} from "@/hooks/useSchedules";
import { useProfiles } from "@/hooks/useProfiles";
import { useToast } from "@/hooks/useToast";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import ScheduleForm from "./schedules/ScheduleForm";
import ScheduleRow from "./schedules/ScheduleRow";
import { useScheduleForm } from "./schedules/useScheduleForm";
import type { CreateScheduleBody } from "@/api/observer";

export default function SchedulesPage() {
  const { data: schedules, isLoading } = useSchedules();
  const { data: profiles } = useProfiles();
  const toggle = useToggleSchedule();
  const del = useDeleteSchedule();
  const run = useRunSchedule();
  const create = useCreateSchedule();
  const update = useUpdateSchedule();
  const updateIncludes = useUpdateScheduleIncludes();
  const { push } = useToast();

  const [showForm, setShowForm] = useState(false);
  const form = useScheduleForm();

  // Default to the first profile once loaded. Render-phase guarded update
  // (React's "adjust state when data changes") rather than an effect, which
  // avoids react-hooks/set-state-in-effect cascading renders.
  if (form.profileId === null && profiles && profiles.length > 0) {
    form.setProfileId(profiles[0].id);
  }

  const profileFor = (id: number) => profiles?.find((p) => p.id === id);
  const profileName = (id: number) => profileFor(id)?.name ?? `#${id}`;
  const onError = (e: unknown) => push({ kind: "error", text: (e as Error).message });

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.profileId) return;
    try {
      // The backend rejects a foreign override model and a non-Claude batch schedule;
      // without this the 400 would leave the form looking simply unresponsive.
      await create.mutateAsync(form.payload());
      form.reset();
      setShowForm(false);
    } catch (e) {
      onError(e);
    }
  }

  /** The one save path for an existing schedule — every writable field, not a subset. */
  const onSave = (id: number, body: CreateScheduleBody, onSuccess: () => void) =>
    update.mutate({ id, body }, { onSuccess, onError });

  if (isLoading) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">Observer schedules</h1>
        <SkeletonRows rows={3} />
      </main>
    );
  }

  const rows = Array.isArray(schedules) ? schedules : [];

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6 ledger-fade-in">
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
            profileFor={profileFor}
            isSaving={update.isPending}
            onToggle={(id, en) => toggle.mutate({ id, enabled: en })}
            onRun={(id) =>
              run.mutate(id, {
                onSuccess: () =>
                  push({ kind: "info", text: "Fired — results land on the observer timeline." }),
                onError,
              })
            }
            onDelete={(id) => del.mutate(id)}
            onSaveSections={(id, includes) =>
              updateIncludes.mutate({ id, default_includes: includes })}
            onSave={onSave}
          />
        ))}
      </ul>

      <button
        type="button"
        onClick={() => setShowForm((v) => !v)}
        className="ledger-ghost"
      >
        {showForm ? "Cancel" : "+ New schedule"}
      </button>

      {showForm && (
        <ScheduleForm
          idPrefix="sched-new"
          profiles={profiles}
          isPending={create.isPending}
          onSubmit={onCreate}
          form={form}
          submitLabel="Create"
          pendingLabel="Creating…"
        />
      )}
    </main>
  );
}
