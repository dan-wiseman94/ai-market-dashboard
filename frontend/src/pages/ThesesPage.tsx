import { Link } from "react-router-dom";
import { useTheses } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import type { Thesis, ThesisStatus } from "@/api/thesis";

const STATUS_BADGE: Record<ThesisStatus, { label: string; className: string }> = {
  open: {
    label: "Open",
    className:
      "bg-copper-500/20 text-copper-300 border border-copper-500/40",
  },
  closed_win: {
    label: "Win",
    className:
      "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40",
  },
  closed_loss: {
    label: "Loss",
    className:
      "bg-rose-900/40 text-rose-300 border border-rose-700/40",
  },
  closed_scratch: {
    label: "Scratch",
    className:
      "bg-neutral-800/60 text-neutral-400 border border-neutral-700/40",
  },
  invalidated: {
    label: "Invalidated",
    className:
      "bg-amber-900/30 text-amber-300 border border-amber-700/40",
  },
};

const DIRECTION_LABEL: Record<string, string> = {
  bullish: "↑ Bullish",
  bearish: "↓ Bearish",
  neutral: "— Neutral",
};

const DIRECTION_CLASS: Record<string, string> = {
  bullish: "text-emerald-400",
  bearish: "text-rose-400",
  neutral: "text-neutral-400",
};

function StatusBadge({ status }: { status: ThesisStatus }) {
  const { label, className } = STATUS_BADGE[status];
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium ${className}`}
      data-testid={`status-badge-${status}`}
    >
      {label}
    </span>
  );
}

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
