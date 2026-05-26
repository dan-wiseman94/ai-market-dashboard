import { Link } from "react-router-dom";
import { useTheses } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge, DIRECTION_LABEL, DIRECTION_CLASS } from "@/components/thesis/ThesisBadges";
import type { Thesis } from "@/api/thesis";

function ThesisRow({ thesis }: { thesis: Thesis }) {
  return (
    <li
      data-testid={`thesis-row-${thesis.id}`}
      className="flex items-center gap-4 px-4 py-3 rounded border border-rule hover:border-rule-soft hover:bg-copper-500/[0.03] transition-colors"
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

export default function ThesesPage() {
  const { data: theses, isLoading } = useTheses();

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <SkeletonRows rows={5} />
      </div>
    );
  }

  const all = theses ?? [];
  const open = all.filter((t) => t.status === "open");
  const closed = all.filter((t) => t.status !== "open");

  if (all.length === 0) {
    return (
      <main className="max-w-4xl mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
            Theses
          </h1>
        </div>
        <EmptyState
          title="No theses yet"
          body="Track your market calls by creating a thesis from a thread or directly here."
        />
      </main>
    );
  }

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-8 ledger-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="ledger-display" style={{ fontSize: "1.5rem" }}>
          Theses
        </h1>
        <span className="ledger-eyebrow">
          {open.length} open · {closed.length} closed
        </span>
      </div>

      {open.length > 0 && (
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="ledger-eyebrow">Open</h2>
            <span className="flex-1 h-px bg-rule" />
          </div>
          <ul className="space-y-1.5">
            {open.map((t) => (
              <ThesisRow key={t.id} thesis={t} />
            ))}
          </ul>
        </section>
      )}

      {closed.length > 0 && (
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="ledger-eyebrow">Closed</h2>
            <span className="flex-1 h-px bg-rule" />
          </div>
          <ul className="space-y-1.5">
            {closed.map((t) => (
              <ThesisRow key={t.id} thesis={t} />
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
