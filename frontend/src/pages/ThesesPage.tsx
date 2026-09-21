import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useArchiveThesis, useRestoreThesis, useTheses } from "@/hooks/useTheses";
import { useToast } from "@/hooks/useToast";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge, DIRECTION_LABEL, DIRECTION_CLASS } from "@/components/thesis/ThesisBadges";
import type { Thesis, ThesisListFilter } from "@/api/thesis";

const FILTERS: ReadonlyArray<{ value: ThesisListFilter; label: string }> = [
  { value: "live", label: "Live" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

const EMPTY_BODY: Record<ThesisListFilter, string> = {
  live: "Track your market calls by creating a thesis from a thread or directly here.",
  archived: "Nothing archived. Archiving a thesis hides it here without touching its post-mortems.",
  all: "Track your market calls by creating a thesis from a thread or directly here.",
};

function FilterPicker({
  value,
  onChange,
}: {
  value: ThesisListFilter;
  onChange: (v: ThesisListFilter) => void;
}) {
  const groupName = useId();
  return (
    <fieldset className="flex items-center gap-2">
      <legend className="sr-only">Which theses to show</legend>
      {FILTERS.map((f) => (
        <label
          key={f.value}
          className={`cursor-pointer rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors focus-within:ring-1 focus-within:ring-copper-400 ${
            value === f.value
              ? "border-copper-500/60 text-ink-100"
              : "border-rule text-ink-400 hover:text-copper-300"
          }`}
        >
          <input
            type="radio"
            name={groupName}
            value={f.value}
            checked={value === f.value}
            onChange={() => onChange(f.value)}
            className="sr-only"
          />
          {f.label}
        </label>
      ))}
    </fieldset>
  );
}

function ThesisRow({
  thesis,
  onArchive,
  onRestore,
  pending,
}: {
  thesis: Thesis;
  onArchive: (t: Thesis) => void;
  onRestore: (t: Thesis) => void;
  pending: boolean;
}) {
  const archived = thesis.archived_at !== null;
  return (
    <li
      data-testid={`thesis-row-${thesis.id}`}
      className={`flex items-center gap-4 px-4 py-3 rounded border border-rule hover:border-rule-soft hover:bg-copper-500/[0.03] transition-colors ${
        archived ? "opacity-70" : ""
      }`}
    >
      <div className="flex-1 min-w-0">
        <Link
          to={`/theses/${thesis.id}`}
          className="font-medium text-ink-100 hover:text-copper-300 transition-colors truncate block"
        >
          {thesis.title}
        </Link>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-[11px] text-copper-400 uppercase tracking-wide">
            {thesis.ticker}
          </span>
          <span
            className={`font-mono text-[11px] ${DIRECTION_CLASS[thesis.direction]}`}
          >
            {DIRECTION_LABEL[thesis.direction]}
          </span>
          {archived && (
            <span
              data-testid={`archived-badge-${thesis.id}`}
              className="font-mono text-[10px] uppercase tracking-loose2 border border-rule px-1 py-0.5 rounded-ledger text-ink-500"
            >
              Archived
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span
          className="font-mono text-[11px] text-ink-400"
          title="Conviction"
          aria-label={`Conviction ${thesis.conviction}`}
        >
          {"★".repeat(thesis.conviction)}
          {"☆".repeat(5 - thesis.conviction)}
        </span>
        <StatusBadge status={thesis.status} />
        <button
          type="button"
          disabled={pending}
          onClick={() => (archived ? onRestore(thesis) : onArchive(thesis))}
          aria-label={`${archived ? "Restore" : "Archive"} ${thesis.title}`}
          className="font-mono text-[11px] uppercase tracking-wider text-ink-400 hover:text-copper-300 transition-colors disabled:opacity-40"
        >
          {archived ? "Restore" : "Archive"}
        </button>
        <Link
          to={`/theses/${thesis.id}`}
          className="font-mono text-[11px] text-ink-500 hover:text-copper-300 transition-colors"
          aria-label={`View thesis ${thesis.title}`}
        >
          →
        </Link>
      </div>
    </li>
  );
}

function ThesisSection({
  title,
  theses,
  renderRow,
}: {
  title: string;
  theses: Thesis[];
  renderRow: (t: Thesis) => ReactNode;
}) {
  if (theses.length === 0) return null;
  return (
    <section>
      <div className="flex items-center gap-3 mb-3">
        <h2 className="ledger-eyebrow">{title}</h2>
        <span className="flex-1 h-px bg-rule" />
      </div>
      <ul className="space-y-1.5">{theses.map(renderRow)}</ul>
    </section>
  );
}

export default function ThesesPage() {
  const [filter, setFilter] = useState<ThesisListFilter>("live");
  const { data: theses, isLoading } = useTheses(filter);
  const archive = useArchiveThesis();
  const restore = useRestoreThesis();
  const { push } = useToast();

  const pending = archive.isPending || restore.isPending;

  const onArchive = (t: Thesis) =>
    archive.mutate(t.id, {
      onSuccess: () =>
        push({ kind: "success", text: `Archived “${t.title}”. Its post-mortems are kept.` }),
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });

  const onRestore = (t: Thesis) =>
    restore.mutate(t.id, {
      onSuccess: () =>
        push({ kind: "success", text: `Restored “${t.title}”. The price guard stays off.` }),
      onError: (e) => push({ kind: "error", text: (e as Error).message }),
    });

  const renderRow = (t: Thesis) => (
    <ThesisRow
      key={t.id}
      thesis={t}
      onArchive={onArchive}
      onRestore={onRestore}
      pending={pending}
    />
  );

  const header = (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
        Theses
      </h1>
      <FilterPicker value={filter} onChange={setFilter} />
    </div>
  );

  if (isLoading) {
    return (
      <main className="max-w-4xl mx-auto p-6 space-y-6">
        {header}
        <SkeletonRows rows={5} />
      </main>
    );
  }

  const all = theses ?? [];
  const open = all.filter((t) => t.status === "open");
  const closed = all.filter((t) => t.status !== "open");

  if (all.length === 0) {
    return (
      <main className="max-w-4xl mx-auto p-6 space-y-6">
        {header}
        <EmptyState
          title={filter === "archived" ? "No archived theses" : "No theses yet"}
          body={EMPTY_BODY[filter]}
        />
      </main>
    );
  }

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-8 ledger-fade-in">
      {header}
      <p className="ledger-eyebrow">
        {open.length} open · {closed.length} closed
      </p>

      <ThesisSection title="Open" theses={open} renderRow={renderRow} />
      <ThesisSection title="Closed" theses={closed} renderRow={renderRow} />
    </main>
  );
}
