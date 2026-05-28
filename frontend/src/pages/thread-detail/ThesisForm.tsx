import type { ThesisDirection } from "@/api/thesis";

const FIELD_CLASS =
  "bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500";

type Props = {
  promoteMode: boolean;
  title: string;
  onTitleChange: (v: string) => void;
  ticker: string;
  onTickerChange: (v: string) => void;
  direction: ThesisDirection;
  onDirectionChange: (v: ThesisDirection) => void;
  conviction: number;
  onConvictionChange: (v: number) => void;
  target: string;
  onTargetChange: (v: string) => void;
  invalidation: string;
  onInvalidationChange: (v: string) => void;
  pending: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
};

export default function ThesisForm({
  promoteMode,
  title,
  onTitleChange,
  ticker,
  onTickerChange,
  direction,
  onDirectionChange,
  conviction,
  onConvictionChange,
  target,
  onTargetChange,
  invalidation,
  onInvalidationChange,
  pending,
  onSubmit,
  onCancel,
}: Props) {
  return (
    <form
      onSubmit={onSubmit}
      className="ledger-surface px-5 py-4 mb-8 space-y-4"
      data-testid="new-thesis-form"
    >
      <div className="ledger-eyebrow mb-1">{promoteMode ? "Promote to thesis" : "New thesis from this thread"}</div>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label htmlFor="thesis-title" className="block text-[12px] text-ink-400 mb-1">Title</label>
          <input
            id="thesis-title"
            required
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g. SPY breaks 600 by Q3"
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="thesis-ticker" className="block text-[12px] text-ink-400 mb-1">Ticker</label>
          <input
            id="thesis-ticker"
            required
            value={ticker}
            onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
            placeholder="SPY"
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="thesis-direction" className="block text-[12px] text-ink-400 mb-1">Direction</label>
          <select
            id="thesis-direction"
            value={direction}
            onChange={(e) => onDirectionChange(e.target.value as ThesisDirection)}
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
          >
            <option value="bullish">Bullish</option>
            <option value="bearish">Bearish</option>
            <option value="neutral">Neutral</option>
          </select>
        </div>
        <div>
          <label htmlFor="thesis-conviction" className="block text-[12px] text-ink-400 mb-1">Conviction (1–5)</label>
          <input
            id="thesis-conviction"
            type="number"
            min={1}
            max={5}
            value={conviction}
            onChange={(e) => onConvictionChange(Number(e.target.value))}
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
          />
        </div>
        <div>
          <label htmlFor="thesis-target" className="block text-[12px] text-ink-400 mb-1">Target price (optional)</label>
          <input
            id="thesis-target"
            value={target}
            onChange={(e) => onTargetChange(e.target.value)}
            placeholder="600.00"
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="thesis-invalidation" className="block text-[12px] text-ink-400 mb-1">Invalidation price (optional)</label>
          <input
            id="thesis-invalidation"
            value={invalidation}
            onChange={(e) => onInvalidationChange(e.target.value)}
            placeholder="540.00"
            className={FIELD_CLASS}
          />
        </div>
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={pending}
          className="ledger-cta px-4 py-1.5 text-[13px]"
        >
          {pending ? "Creating…" : "Create thesis"}
        </button>
        <button
          type="button"
          className="ledger-ghost px-4 py-1.5 text-[13px]"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
