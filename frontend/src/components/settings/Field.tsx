// frontend/src/components/settings/Field.tsx
import { useId } from "react";
import type { ReactNode } from "react";

type FieldProps = {
  label: string;
  hint?: string;
  error?: string;
  children: (props: { id: string; describedBy?: string }) => ReactNode;
};

export default function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [error ? errId : hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block font-mono text-[10px] uppercase tracking-loose2 text-copper-400"
      >
        {label}
      </label>
      {children({ id, describedBy })}
      {hint && !error && <p id={hintId} className="text-[11px] text-ink-400">{hint}</p>}
      {error && <p id={errId} className="text-[11px] text-loss">{error}</p>}
    </div>
  );
}
