type ToggleProps = {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Accessible name. Used as `aria-label` unless `labelledBy` names visible text. */
  label: string;
  disabled?: boolean;
  id?: string;
  /** Id of visible text that names the switch; wins over `label`. */
  labelledBy?: string;
  /** Id of the hint that describes the switch, announced after its name. */
  describedBy?: string;
};

export default function Toggle({
  checked,
  onChange,
  label,
  disabled,
  id,
  labelledBy,
  describedBy,
}: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      // A visible label is the better name when there is one; `label` stays the
      // fallback so every caller that passes only a label is unaffected.
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors",
        "border-rule disabled:opacity-50",
        checked ? "bg-copper-600" : "bg-ink-700",
      ].join(" ")}
    >
      <span
        aria-hidden
        className={[
          "inline-block h-3.5 w-3.5 transform rounded-full bg-ink-50 transition-transform duration-150 ease-ledger",
          checked ? "translate-x-[18px]" : "translate-x-[3px]",
        ].join(" ")}
      />
    </button>
  );
}
