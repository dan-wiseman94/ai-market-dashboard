import type { ReactNode } from "react";
import type { FeatureGroupMeta, FeatureItem, FeatureValue } from "@/api/features";
import FeatureRow from "./FeatureRow";

type Props = {
  group: FeatureGroupMeta;
  items: FeatureItem[];
  /** The key of the row currently being written, if any. */
  pendingKey?: string;
  /** Row key -> labels of the rows it depends on that are currently off. */
  unmetRequires?: Record<string, string[]>;
  onSave: (item: FeatureItem, value: FeatureValue) => void;
  /** Shown instead of the rows when a filter hides all of them. */
  empty?: ReactNode;
};

/**
 * One section of the Features page.
 *
 * A `fieldset` + `legend` rather than a heading plus a div: the legend is the group's
 * accessible name for every control inside it, which is what stops ~90 switches from
 * being an undifferentiated list to a screen reader. The legend is therefore the only
 * heading — a duplicate `h3` would read the title twice.
 */
export default function FeatureGroup({
  group,
  items,
  pendingKey,
  unmetRequires,
  onSave,
  empty,
}: Props) {
  return (
    <fieldset className="border-0 p-0 m-0" data-testid={`feature-group-${group.key}`}>
      <legend className="mb-1 font-display text-[1.05rem] text-ink-50">{group.label}</legend>
      <p className="mb-3 text-[12px] text-ink-400">{group.blurb}</p>
      {items.length === 0 ? (
        <div className="text-[12px] text-ink-400">{empty ?? "Nothing here matches."}</div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <FeatureRow
              key={item.key}
              item={item}
              pending={pendingKey === item.key}
              unmetRequires={unmetRequires?.[item.key]}
              onSave={(value) => onSave(item, value)}
            />
          ))}
        </div>
      )}
    </fieldset>
  );
}
