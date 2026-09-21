/**
 * Investigate opt-in, shared by observer schedules and event triggers.
 *
 * Investigate is not a free flag: a fire runs a bounded autonomous tool loop
 * (several extra model round-trips per fire) instead of one observation, so the
 * control always ships the cost note beside it rather than a bare checkbox.
 */

type Props = {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Unique per rendered instance — a create form and an edit form can be open together. */
  idPrefix: string;
  /** Extra caveat appended under the cost note (e.g. "plain mode only"). */
  note?: string;
  /** Greyed out when the mode ignores it (structured fires never investigate). */
  disabled?: boolean;
};

export default function InvestigateToggle({
  checked, onChange, idPrefix, note, disabled,
}: Props) {
  const inputId = `${idPrefix}-investigate`;
  const descId = `${idPrefix}-investigate-desc`;
  return (
    <div className="space-y-1">
      <label
        className={`flex items-center gap-2 text-sm ${disabled ? "text-ink-500" : ""}`}
        htmlFor={inputId}
      >
        <input
          id={inputId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-describedby={descId}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>Investigate (autonomous tool loop — spends money)</span>
      </label>
      <p id={descId} className="text-xs text-ink-500">
        Each fire runs a bounded tool-using investigation instead of a single
        observation: several extra model calls and tool round-trips, so it costs
        materially more per fire. Spend is bounded by the investigation iteration
        limit and the separate autonomous daily cost ceiling
        (AI_AUTONOMOUS_DAILY_CAP_USD).{note ? ` ${note}` : ""}
      </p>
    </div>
  );
}
