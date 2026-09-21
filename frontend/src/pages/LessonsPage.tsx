import { useMemo, useState } from "react";

import {
  LESSON_DIRECTIONS,
  MIN_LESSON_SUPPORT,
  type Lesson,
  type LessonFilters,
  type LessonTags,
} from "@/api/lessons";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  useCreateLesson,
  useDeleteLesson,
  useLessons,
  useUpdateLesson,
} from "@/hooks/useLessons";
import { useToast } from "@/hooks/useToast";

type TriState = "any" | "yes" | "no";
type FilterKey = "visible" | "pinned" | "muted";

/** Each filter says what "yes" and "no" mean in its own words — "Any / Yes / No"
 * against a legend of "Coach visibility" reads as a riddle. */
const FILTER_FIELDS: Array<{
  key: FilterKey;
  label: string;
  yes: string;
  no: string;
}> = [
  { key: "visible", label: "Coach visibility", yes: "Reaching", no: "Filtered out" },
  { key: "pinned", label: "Pinned", yes: "Pinned", no: "Not pinned" },
  { key: "muted", label: "Muted", yes: "Muted", no: "Not muted" },
];

function triToFlag(value: TriState): boolean | undefined {
  if (value === "yes") return true;
  if (value === "no") return false;
  return undefined;
}

function splitList(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function tagList(tags: LessonTags): string[] {
  return [...(tags.directions ?? []), ...(tags.sectors ?? [])];
}

function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Why a lesson is, or is not, reaching the Coach — the rule spelled out per row
 * rather than left for the reader to re-derive from support_n/pinned/muted. */
function visibilityReason(lesson: Lesson): string {
  if (lesson.muted) return "Muted — excluded by hand.";
  if (lesson.pinned) return "Pinned — reaches the Coach regardless of support.";
  if (lesson.support_n >= MIN_LESSON_SUPPORT) {
    return `Backed by ${lesson.support_n} post-mortems.`;
  }
  return `Only ${lesson.support_n} of ${MIN_LESSON_SUPPORT} supporting post-mortems — pin it to override.`;
}

/**
 * What deleting this row actually costs, quoted back so a mis-click can be caught
 * before it lands. A distilled lesson is reconstructible — the distill beat still
 * holds the post-mortems it came from — but a hand-written one carries no evidence
 * and the row is the only copy of the text.
 */
function deleteLessonConfirm(lesson: Lesson): string {
  const fate =
    lesson.support_n > 0
      ? `It was distilled from ${lesson.support_n} post-mortem${lesson.support_n === 1 ? "" : "s"}, so the distill beat can write it again from that evidence.`
      : "It is hand-written: no post-mortem backs it, so nothing regenerates it. This deletes the only copy of that text, permanently.";
  return `Delete this lesson?\n\n\u201c${lesson.text}\u201d\n\n${fate}`;
}

function VisibilityBadge({ lesson }: { lesson: Lesson }) {
  const reaching = lesson.visible_to_coach;
  return (
    <span
      className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${
        reaching
          ? "bg-gain-500/15 text-gain-400"
          : "border border-rule text-ink-500"
      }`}
    >
      {reaching ? "Reaching the Coach" : "Not reaching the Coach"}
    </span>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Record<FilterKey, TriState>;
  onChange: (key: FilterKey, value: TriState) => void;
}) {
  return (
    <fieldset className="flex flex-wrap items-end gap-4 rounded border border-rule p-3">
      <legend className="px-1 text-xs uppercase tracking-wide text-ink-500">
        Filter lessons
      </legend>
      {FILTER_FIELDS.map(({ key, label, yes, no }) => (
        <label key={key} className="flex flex-col gap-1 text-xs text-ink-400">
          {label}
          <select
            value={filters[key]}
            onChange={(e) => onChange(key, e.target.value as TriState)}
            className="rounded border border-rule bg-transparent px-2 py-1 text-sm text-ink-200"
          >
            <option value="any">Any</option>
            <option value="yes">{yes}</option>
            <option value="no">{no}</option>
          </select>
        </label>
      ))}
    </fieldset>
  );
}

function LessonComposer() {
  const create = useCreateLesson();
  const { push } = useToast();
  const [text, setText] = useState("");
  const [directions, setDirections] = useState<string[]>([]);
  const [sectors, setSectors] = useState("");

  function toggleDirection(d: string) {
    setDirections((xs) => (xs.includes(d) ? xs.filter((x) => x !== d) : [...xs, d]));
  }

  const sectorList = splitList(sectors);
  const canSubmit =
    text.trim().length > 0 && (directions.length > 0 || sectorList.length > 0);

  function onSubmit() {
    create.mutate(
      {
        text: text.trim(),
        tags: { directions, sectors: sectorList },
        pinned: true,
      },
      {
        onSuccess: () => {
          setText("");
          setDirections([]);
          setSectors("");
          push({ kind: "success", text: "Lesson written — pinned so the Coach reads it." });
        },
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  }

  return (
    <fieldset className="space-y-3 rounded border border-rule p-4">
      <legend className="px-1 text-xs uppercase tracking-wide text-ink-500">
        Write a lesson
      </legend>
      <p id="composer-help" className="text-sm text-ink-400">
        A hand-written lesson carries no post-mortem evidence, so its support stays at 0
        and the Coach would never read it. New lessons are therefore created pinned.
      </p>
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Lesson
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          aria-describedby="composer-help"
          placeholder="e.g. I size up into a gap and give it all back by the close."
          className="rounded border border-rule bg-transparent px-3 py-2 text-sm text-ink-200"
        />
      </label>
      <fieldset className="flex flex-wrap items-center gap-3">
        <legend className="text-xs text-ink-400">Directions</legend>
        {LESSON_DIRECTIONS.map((d) => (
          <label key={d} className="flex items-center gap-1.5 text-sm text-ink-300">
            <input
              type="checkbox"
              checked={directions.includes(d)}
              onChange={() => toggleDirection(d)}
            />
            {d}
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1 text-xs text-ink-400">
        Sectors
        <input
          value={sectors}
          onChange={(e) => setSectors(e.target.value)}
          aria-describedby="sectors-help"
          placeholder="Energy, Technology"
          className="rounded border border-rule bg-transparent px-3 py-2 text-sm text-ink-200"
        />
      </label>
      <p id="sectors-help" className="text-xs text-ink-500">
        Comma-separated. The Coach matches on direction or sector — a lesson tagged with
        neither can never be surfaced, so at least one is required.
      </p>
      <button
        type="button"
        onClick={onSubmit}
        disabled={!canSubmit || create.isPending}
        className="rounded bg-copper-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {create.isPending ? "Saving…" : "Add lesson"}
      </button>
    </fieldset>
  );
}

function LessonRow({ lesson }: { lesson: Lesson }) {
  const update = useUpdateLesson();
  const remove = useDeleteLesson();
  const { push } = useToast();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(lesson.text);

  const onError = (e: unknown) => push({ kind: "error", text: (e as Error).message });

  function patch(body: { text?: string; pinned?: boolean; muted?: boolean }) {
    update.mutate({ id: lesson.id, patch: body }, { onError });
  }

  function saveEdit() {
    const text = draft.trim();
    if (!text) return;
    update.mutate(
      { id: lesson.id, patch: { text } },
      {
        onSuccess: () => {
          setEditing(false);
          push({ kind: "success", text: "Lesson updated." });
        },
        onError,
      },
    );
  }

  const tags = tagList(lesson.tags ?? {});

  return (
    <li
      data-testid={`lesson-${lesson.id}`}
      className="space-y-2 rounded border border-rule p-3"
    >
      <div className="flex items-start justify-between gap-3">
        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            aria-label={`Edit lesson ${lesson.id}`}
            className="flex-1 rounded border border-rule bg-transparent px-2 py-1 text-sm text-ink-200"
          />
        ) : (
          <p className="flex-1 text-sm text-ink-200">{lesson.text}</p>
        )}
        <VisibilityBadge lesson={lesson} />
      </div>

      <p className="text-xs text-ink-500">{visibilityReason(lesson)}</p>

      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
        {tags.length > 0 ? (
          tags.map((t) => (
            <span key={t} className="rounded border border-rule px-1.5 py-0.5">
              {t}
            </span>
          ))
        ) : (
          <span>untagged — the Coach can never match it</span>
        )}
        <span>· support {lesson.support_n}</span>
        <span>· last seen {fmtDate(lesson.last_seen)}</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {editing ? (
          <>
            <button
              type="button"
              onClick={saveEdit}
              disabled={update.isPending}
              className="rounded border border-rule px-2 py-1 text-xs text-ink-300 hover:text-copper-300 disabled:opacity-50"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(lesson.text);
                setEditing(false);
              }}
              className="rounded border border-rule px-2 py-1 text-xs text-ink-400 hover:text-ink-200"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded border border-rule px-2 py-1 text-xs text-ink-300 hover:text-copper-300"
          >
            Edit
          </button>
        )}
        <button
          type="button"
          onClick={() => patch({ pinned: !lesson.pinned })}
          disabled={update.isPending}
          className="rounded border border-rule px-2 py-1 text-xs text-ink-300 hover:text-copper-300 disabled:opacity-50"
        >
          {lesson.pinned ? "Unpin" : "Pin"}
        </button>
        <button
          type="button"
          onClick={() => patch({ muted: !lesson.muted })}
          disabled={update.isPending}
          className="rounded border border-rule px-2 py-1 text-xs text-ink-300 hover:text-copper-300 disabled:opacity-50"
        >
          {lesson.muted ? "Unmute" : "Mute"}
        </button>
        <button
          type="button"
          onClick={() => {
            if (!window.confirm(deleteLessonConfirm(lesson))) return;
            remove.mutate(lesson.id, {
              onSuccess: () => push({ kind: "success", text: "Lesson deleted." }),
              onError,
            });
          }}
          disabled={remove.isPending}
          className="rounded border border-rule px-2 py-1 text-xs text-copper-400 hover:text-copper-300 disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

export default function LessonsPage() {
  const [tri, setTri] = useState<Record<FilterKey, TriState>>({
    visible: "any",
    pinned: "any",
    muted: "any",
  });

  const filters: LessonFilters = useMemo(
    () => ({
      visible: triToFlag(tri.visible),
      pinned: triToFlag(tri.pinned),
      muted: triToFlag(tri.muted),
    }),
    [tri],
  );

  const filtered = Object.values(tri).some((v) => v !== "any");
  const { data: lessons, isLoading, isError } = useLessons(filters);
  const rows = lessons ?? [];
  const reaching = rows.filter((l) => l.visible_to_coach).length;

  return (
    <main className="mx-auto max-w-4xl space-y-5 p-6 ledger-fade-in">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink-100">Lessons</h1>
        <p className="max-w-2xl text-sm text-ink-400">
          What the post-mortems keep teaching, distilled into standing rules. The Decision
          Coach only reads a lesson once it recurs across at least {MIN_LESSON_SUPPORT}{" "}
          post-mortems — below that it is filtered out, and pinning is the override.
        </p>
      </header>

      <LessonComposer />

      <FilterBar
        filters={tri}
        onChange={(key, value) => setTri((prev) => ({ ...prev, [key]: value }))}
      />

      {isLoading ? (
        <SkeletonRows rows={4} />
      ) : isError ? (
        <EmptyState
          title="Couldn’t load lessons"
          body="The lessons endpoint didn’t answer. Retry in a moment."
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={filtered ? "No lessons match these filters" : "No lessons yet"}
          body={
            filtered
              ? "Set every filter back to “Any” to see the whole set."
              : "Post-mortems distil into lessons as theses resolve — or write a standing rule of your own above."
          }
        />
      ) : (
        <>
          <p className="text-xs text-ink-500">
            Reaching the Coach: {reaching} of {rows.length} shown.
          </p>
          <ul className="space-y-2">
            {rows.map((l) => (
              <LessonRow key={l.id} lesson={l} />
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
