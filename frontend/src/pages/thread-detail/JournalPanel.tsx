import { Link } from "react-router-dom";
import type { JournalDecision, JournalEntry } from "@/api/journal";
import { EmptyState } from "@/components/EmptyState";

// Per-decision pill colors. The original used a nested ternary keyed on the four
// decisions (acted/passed/watching/hedged); the lookup keeps the exact classes
// while dropping the nesting. `hedged` was the ternary's trailing else branch.
const DECISION_PILL_CLASS: Record<JournalDecision, string> = {
  acted:
    "text-emerald-700 border-emerald-500/40 bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-800 dark:bg-emerald-950/40",
  passed: "text-slate-400 border-slate-700 bg-slate-900/40",
  watching:
    "text-amber-700 border-amber-500/40 bg-amber-500/10 dark:text-amber-400 dark:border-amber-800 dark:bg-amber-950/40",
  hedged:
    "text-violet-700 border-violet-500/40 bg-violet-500/10 dark:text-violet-400 dark:border-violet-800 dark:bg-violet-950/40",
};

type Props = {
  decision: JournalDecision;
  onDecisionChange: (v: JournalDecision) => void;
  note: string;
  onNoteChange: (v: string) => void;
  pending: boolean;
  onLogDecision: () => void;
  onPromote: () => void;
  onClose: () => void;
  entries: JournalEntry[];
};

export default function JournalPanel({
  decision,
  onDecisionChange,
  note,
  onNoteChange,
  pending,
  onLogDecision,
  onPromote,
  onClose,
  entries,
}: Props) {
  return (
    <div
      className="ledger-surface px-5 py-4 mb-8 space-y-4"
      data-testid="journal-panel"
    >
      <div className="ledger-eyebrow mb-1">Close &amp; journal this thread</div>

      {/* Decision log form */}
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label htmlFor="journal-decision" className="block text-[12px] text-ink-400 mb-1">Decision</label>
          <select
            id="journal-decision"
            value={decision}
            onChange={(e) => onDecisionChange(e.target.value as JournalDecision)}
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
            data-testid="journal-decision-select"
          >
            <option value="acted">Acted</option>
            <option value="passed">Passed</option>
            <option value="watching">Watching</option>
            <option value="hedged">Hedged</option>
          </select>
        </div>
        <div className="col-span-2">
          <label htmlFor="journal-note" className="block text-[12px] text-ink-400 mb-1">Note (optional)</label>
          <textarea
            id="journal-note"
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
            placeholder="What did you decide and why?"
            rows={3}
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500 resize-none"
            data-testid="journal-note-textarea"
          />
        </div>
      </div>
      <div className="flex gap-2 pt-1 flex-wrap">
        <button
          type="button"
          disabled={pending}
          onClick={onLogDecision}
          className="ledger-cta px-4 py-1.5 text-[13px]"
          data-testid="journal-log-btn"
        >
          {pending ? "Logging…" : "Log decision"}
        </button>
        <button
          type="button"
          onClick={onPromote}
          className="ledger-ghost px-4 py-1.5 text-[13px]"
          data-testid="journal-promote-btn"
        >
          Promote to thesis
        </button>
        <button
          type="button"
          className="ledger-ghost px-4 py-1.5 text-[13px] ml-auto"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      {/* Existing journal entries */}
      <div className="border-t border-rule-soft pt-4 mt-2">
        <div className="ledger-eyebrow mb-3">Prior decisions</div>
        {entries.length === 0 ? (
          <EmptyState title="No decisions logged yet" body="Use the form above to record what you decided on this thread." />
        ) : (
          <ul className="space-y-3" data-testid="journal-entries-list">
            {entries.map((entry) => (
              <li key={entry.id} className="flex items-start gap-3 py-2 border-b border-rule-soft last:border-b-0" data-testid={`journal-entry-${entry.id}`}>
                <span className={`font-mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border shrink-0 mt-0.5 ${DECISION_PILL_CLASS[entry.decision]}`}>
                  {entry.decision}
                </span>
                <div className="flex-1 min-w-0">
                  {entry.note && (
                    <p className="text-[13px] text-ink-100 leading-relaxed mb-1">{entry.note}</p>
                  )}
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-mono text-[11px] text-ink-500">
                      {new Date(entry.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                    </span>
                    {entry.thesis_id != null && (
                      <Link
                        to={`/theses/${entry.thesis_id}`}
                        className="font-mono text-[11px] text-copper-300 hover:text-copper-200 transition-colors"
                        data-testid={`journal-thesis-link-${entry.id}`}
                      >
                        → Thesis #{entry.thesis_id}
                      </Link>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
