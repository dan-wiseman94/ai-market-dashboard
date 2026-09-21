import { useId, useState } from "react";

import type { BriefingConfig } from "@/api/briefing";
import { SkeletonRows } from "@/components/Skeleton";
import { useBriefingConfig } from "@/hooks/useBriefing";
import { useProfiles } from "@/hooks/useProfiles";
import { useToast } from "@/hooks/useToast";

const INPUT =
  "rounded border border-rule bg-ink-850 px-2 py-1 text-sm text-ink-100 " +
  "focus:outline-none focus:ring-1 focus:ring-copper-400";

/** Django serialises a TimeField as HH:MM:SS; `<input type="time">` wants HH:MM. */
function toTimeInput(v: string): string {
  return (v || "").slice(0, 5);
}

function NumberRow({
  label, hint, value, min, max, onChange,
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs uppercase tracking-wide text-ink-400">
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        className={`${INPUT} w-28`}
        aria-describedby={`${id}-hint`}
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value);
          // An empty or half-typed box parses as NaN; keep the last good value
          // rather than PATCHing a null the serializer would reject.
          if (!Number.isNaN(n)) onChange(n);
        }}
      />
      <p id={`${id}-hint`} className="text-[11px] text-ink-400">{hint}</p>
    </div>
  );
}

function CheckRow({
  label, hint, checked, onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          aria-describedby={`${id}-hint`}
          onChange={(e) => onChange(e.target.checked)}
        />
        <label htmlFor={id} className="text-sm text-ink-200">{label}</label>
      </div>
      <p id={`${id}-hint`} className="text-[11px] text-ink-400">{hint}</p>
    </div>
  );
}

export default function BriefingSettingsPanel() {
  const { data: config, isLoading, isError, update } = useBriefingConfig();
  const { data: profiles } = useProfiles();
  const { push } = useToast();
  const [draft, setDraft] = useState<Partial<BriefingConfig>>({});
  const timeId = useId();
  const profileId = useId();

  if (isLoading) return <SkeletonRows rows={4} />;
  if (isError || !config) {
    return <p className="text-sm text-loss">Briefing settings could not be loaded.</p>;
  }

  // Draft wins over the server copy so a field stays where the user put it
  // while other fields keep showing the saved value.
  const view: BriefingConfig = { ...config, ...draft };
  const dirty = Object.keys(draft).length > 0;
  const set = <K extends keyof BriefingConfig>(key: K, value: BriefingConfig[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const onSave = () => {
    update.mutate(draft, {
      onSuccess: () => {
        setDraft({});
        push({ kind: "success", text: "Briefing settings saved." });
      },
      onError: (err: Error) =>
        push({ kind: "error", text: `Could not save briefing settings: ${err.message}` }),
    });
  };

  return (
    <section>
      <fieldset className="rounded border border-rule p-4 space-y-4">
        <legend className="px-1 text-xs uppercase tracking-wide text-ink-500">
          Briefing settings
        </legend>

        <CheckRow
          label="Run the morning briefing automatically"
          hint={
            "Once a day, on the schedule below, the briefing assembles your open theses, " +
            "upcoming events, overnight triggers and news. Assembling costs nothing; the AI " +
            "synthesis below is the part that calls a model."
          }
          checked={view.enabled}
          onChange={(v) => set("enabled", v)}
        />

        <CheckRow
          label="Write an AI synthesis for each briefing"
          hint={
            "Adds one paid model call per briefing — about one request a day while the " +
            "schedule above is on. Turn it off to keep every data section and skip the model."
          }
          checked={view.synthesis_enabled}
          onChange={(v) => set("synthesis_enabled", v)}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor={timeId} className="block text-xs uppercase tracking-wide text-ink-400">
              Send at (local)
            </label>
            <input
              id={timeId}
              type="time"
              className={`${INPUT} w-32`}
              aria-describedby={`${timeId}-hint`}
              value={toTimeInput(view.send_at_local)}
              onChange={(e) => set("send_at_local", e.target.value)}
            />
            <p id={`${timeId}-hint`} className="text-[11px] text-ink-400">
              The first scheduled check after this local time fires the day&apos;s briefing.
            </p>
          </div>

          <div className="space-y-1">
            <label
              htmlFor={profileId}
              className="block text-xs uppercase tracking-wide text-ink-400"
            >
              Trading profile
            </label>
            <select
              id={profileId}
              className={`${INPUT} w-full`}
              aria-describedby={`${profileId}-hint`}
              value={view.profile ?? ""}
              onChange={(e) => set("profile", e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">No profile (provider defaults)</option>
              {(profiles ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <p id={`${profileId}-hint`} className="text-[11px] text-ink-400">
              Frames the synthesis in a named style and picks the model it runs on.
            </p>
          </div>

          <NumberRow
            label="News lookback (hours)"
            hint="How far back overnight headlines are gathered."
            value={view.news_lookback_hours}
            min={1}
            max={168}
            onChange={(n) => set("news_lookback_hours", n)}
          />
          <NumberRow
            label="Events within (days)"
            hint="Forward window for earnings and macro events."
            value={view.events_within_days}
            min={1}
            max={60}
            onChange={(n) => set("events_within_days", n)}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            className="rounded border border-rule px-3 py-1 text-sm text-ink-300 hover:text-copper-300 disabled:opacity-50"
            disabled={!dirty || update.isPending}
            onClick={onSave}
          >
            {update.isPending ? "Saving…" : "Save settings"}
          </button>
          <p role="status" className="text-[11px] text-ink-400">
            {dirty ? "Unsaved changes" : "Saved"}
          </p>
        </div>
      </fieldset>
    </section>
  );
}
