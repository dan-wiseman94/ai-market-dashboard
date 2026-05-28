import type { Thesis } from "@/api/thesis";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="ledger-eyebrow mb-0.5">{label}</dt>
      <dd className="text-ink-100 text-[14px]">{children}</dd>
    </div>
  );
}

export function ThesisFields({ thesis }: { thesis: Thesis }) {
  return (
    <dl className="grid grid-cols-2 gap-x-8 gap-y-5 mb-8">
      {thesis.rationale && (
        <div className="col-span-2">
          <Field label="Rationale">{thesis.rationale}</Field>
        </div>
      )}
      {thesis.entry_price && (
        <Field label="Entry price">${thesis.entry_price}</Field>
      )}
      {thesis.target_price && (
        <Field label="Target price">${thesis.target_price}</Field>
      )}
      {thesis.invalidation_price && (
        <Field label="Invalidation price">${thesis.invalidation_price}</Field>
      )}
      {thesis.horizon_days != null && (
        <Field label="Horizon">{thesis.horizon_days} days</Field>
      )}
      <Field label="Opened">
        {new Date(thesis.opened_at).toLocaleDateString()}
      </Field>
      {thesis.closed_at && (
        <Field label="Closed">
          {new Date(thesis.closed_at).toLocaleDateString()}
        </Field>
      )}
      {thesis.close_note && (
        <div className="col-span-2">
          <Field label="Close note">{thesis.close_note}</Field>
        </div>
      )}
    </dl>
  );
}
