import { useCloseThesisForm } from "./useCloseThesisForm";
import type { ThesisStatus } from "@/api/thesis";

const CLOSE_STATUSES: Array<{
  value: Exclude<ThesisStatus, "open">;
  label: string;
}> = [
  { value: "closed_win", label: "Closed — Win" },
  { value: "closed_loss", label: "Closed — Loss" },
  { value: "closed_scratch", label: "Closed — Scratch" },
  { value: "invalidated", label: "Invalidated" },
];

export function CloseThesisForm({ thesisId }: { thesisId: number }) {
  const {
    showForm,
    setShowForm,
    status,
    setStatus,
    note,
    setNote,
    handleSubmit,
    isPending,
  } = useCloseThesisForm(thesisId);

  return (
    <section className="mb-8">
      {!showForm ? (
        <button
          className="ledger-ghost px-4 py-2 text-[13px]"
          onClick={() => setShowForm(true)}
          data-testid="open-close-form-btn"
        >
          Close thesis…
        </button>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="ledger-surface px-5 py-4 space-y-4"
          data-testid="close-thesis-form"
        >
          <div className="ledger-eyebrow mb-1">Close thesis</div>
          <div>
            <label
              htmlFor="close-status"
              className="block text-[12px] text-ink-400 mb-1"
            >
              Outcome
            </label>
            <select
              id="close-status"
              value={status}
              onChange={(e) =>
                setStatus(e.target.value as Exclude<ThesisStatus, "open">)
              }
              className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
            >
              {CLOSE_STATUSES.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="close-note"
              className="block text-[12px] text-ink-400 mb-1"
            >
              Note (optional)
            </label>
            <textarea
              id="close-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="What happened? What did you learn?"
              className="bg-ink-void border border-rule rounded px-3 py-2 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 resize-none placeholder:text-ink-500"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={isPending}
              className="ledger-cta px-4 py-1.5 text-[13px]"
            >
              {isPending ? "Saving…" : "Confirm close"}
            </button>
            <button
              type="button"
              className="ledger-ghost px-4 py-1.5 text-[13px]"
              onClick={() => setShowForm(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
