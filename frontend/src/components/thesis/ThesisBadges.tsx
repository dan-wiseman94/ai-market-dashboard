import type { PostMortemVerdict, ThesisStatus } from "@/api/thesis";

export const STATUS_BADGE: Record<
  ThesisStatus,
  { label: string; className: string }
> = {
  open: {
    label: "Open",
    className: "bg-copper-500/20 text-copper-300 border border-copper-500/40",
  },
  closed_win: {
    label: "Win",
    className:
      "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40",
  },
  closed_loss: {
    label: "Loss",
    className: "bg-rose-900/40 text-rose-300 border border-rose-700/40",
  },
  closed_scratch: {
    label: "Scratch",
    className:
      "bg-neutral-800/60 text-neutral-400 border border-neutral-700/40",
  },
  invalidated: {
    label: "Invalidated",
    className: "bg-amber-900/30 text-amber-300 border border-amber-700/40",
  },
};

export const DIRECTION_LABEL: Record<string, string> = {
  bullish: "↑ Bullish",
  bearish: "↓ Bearish",
  neutral: "— Neutral",
};

export const DIRECTION_CLASS: Record<string, string> = {
  bullish: "text-emerald-400",
  bearish: "text-rose-400",
  neutral: "text-neutral-400",
};

export function StatusBadge({ status }: { status: ThesisStatus }) {
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

export function DirectionLabel({ direction }: { direction: string }) {
  return (
    <span className={`font-mono text-[13px] ${DIRECTION_CLASS[direction] ?? "text-ink-300"}`}>
      {DIRECTION_LABEL[direction] ?? direction}
    </span>
  );
}

const VERDICT_BADGE: Record<
  PostMortemVerdict,
  { label: string; className: string }
> = {
  correct: {
    label: "Correct",
    className:
      "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40",
  },
  incorrect: {
    label: "Incorrect",
    className: "bg-rose-900/40 text-rose-300 border border-rose-700/40",
  },
  mixed: {
    label: "Mixed",
    className: "bg-amber-900/30 text-amber-300 border border-amber-700/40",
  },
  inconclusive: {
    label: "Inconclusive",
    className:
      "bg-neutral-800/60 text-neutral-400 border border-neutral-700/40",
  },
  "": {
    label: "—",
    className:
      "bg-neutral-800/60 text-neutral-400 border border-neutral-700/40",
  },
};

export function VerdictBadge({ verdict }: { verdict: PostMortemVerdict }) {
  const { label, className } = VERDICT_BADGE[verdict] ?? VERDICT_BADGE[""];
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium ${className}`}
      data-testid={`verdict-badge-${verdict || "empty"}`}
    >
      {label}
    </span>
  );
}
