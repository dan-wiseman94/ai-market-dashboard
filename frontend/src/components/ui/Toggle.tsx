// frontend/src/components/ui/Toggle.tsx
type ToggleProps = {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  id?: string;
};

export default function Toggle({ checked, onChange, label, disabled, id }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
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
