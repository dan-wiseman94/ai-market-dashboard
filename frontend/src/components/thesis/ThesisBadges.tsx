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
      "bg-emerald-500/10 text-emerald-700 border border-emerald-500/40 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-700/40",
  },
  closed_loss: {
    label: "Loss",
    className: "bg-rose-500/10 text-rose-700 border border-rose-500/40 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-700/40",
  },
  closed_scratch: {
    label: "Scratch",
    className:
      "bg-neutral-800/60 text-neutral-400 border border-neutral-700/40",
  },
  invalidated: {
    label: "Invalidated",
    className: "bg-amber-500/10 text-amber-700 border border-amber-500/40 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700/40",
  },
};

export const DIRECTION_LABEL: Record<string, string> = {
  bullish: "↑ Bullish",
  bearish: "↓ Bearish",
  neutral: "— Neutral",
};

export const DIRECTION_CLASS: Record<string, string> = {
  bullish: "text-emerald-700 dark:text-emerald-400",
  bearish: "text-rose-700 dark:text-rose-400",
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

const VERDICT_BADGE: Record<
  PostMortemVerdict,
  { label: string; className: string }
> = {
  correct: {
    label: "Correct",
    className:
      "bg-emerald-500/10 text-emerald-700 border border-emerald-500/40 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-700/40",
  },
  incorrect: {
    label: "Incorrect",
    className: "bg-rose-500/10 text-rose-700 border border-rose-500/40 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-700/40",
  },
  mixed: {
    label: "Mixed",
    className: "bg-amber-500/10 text-amber-700 border border-amber-500/40 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700/40",
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
