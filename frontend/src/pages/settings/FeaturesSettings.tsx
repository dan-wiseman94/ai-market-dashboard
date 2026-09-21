import { useId, useMemo, useState } from "react";
import SettingsSection from "@/components/settings/SettingsSection";
import FeatureGroup from "@/components/settings/FeatureGroup";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useFeatures, useSaveFeature } from "@/hooks/useFeatures";
import { useToast } from "@/hooks/useToast";
import { flattenFeatures, type FeatureItem, type FeatureValue } from "@/api/features";
import { FILTERS, matchesFilter, matchesQuery, type FilterId } from "@/lib/featureGroups";

function describeSave(item: FeatureItem, value: FeatureValue): string {
  if (value === null) return `${item.label} reset to its default.`;
  if (typeof value === "boolean") return `${item.label} turned ${value ? "on" : "off"}.`;
  return `${item.label} set to ${String(value)}.`;
}

/**
 * Settings → Features: every switchable capability in the app, in one place.
 *
 * The page is rendered entirely from `GET /api/features/` and hardcodes no feature
 * name — labels, summaries, help, cost notes and even where each write goes all come
 * from the payload, so a capability added to the backend registry appears here with
 * no frontend change. A test asserts this file stays free of feature keys.
 *
 * Saving is per row and immediate. The settings endpoint rejects a whole PATCH body
 * on the first invalid field, so a draft-and-save model across ~90 rows would let one
 * bad value silently discard every other edit.
 */
export default function FeaturesSettings() {
  const { data, isLoading, isError, error } = useFeatures();
  const save = useSaveFeature();
  const { push } = useToast();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterId>("all");
  const [announcement, setAnnouncement] = useState("");

  const all = useMemo(() => (data ? flattenFeatures(data) : []), [data]);
  // A row can declare that it only does anything while another row is on (a cache TTL
  // under its cache, an eval's model under the eval). Say so, rather than letting the
  // user set a number that is then quietly ignored.
  const unmetRequires = useMemo(() => {
    const on = new Map(all.map((i) => [i.key, i.kind === "toggle" ? i.value : true]));
    const labels = new Map(all.map((i) => [i.key, i.label]));
    const out: Record<string, string[]> = {};
    for (const item of all) {
      const unmet = item.requires.filter((r) => on.get(r) === false).map((r) => labels.get(r) ?? r);
      if (unmet.length > 0) out[item.key] = unmet;
    }
    return out;
  }, [all]);
  const shown = useMemo(
    () => all.filter((i) => matchesQuery(i, query) && matchesFilter(i, filter)),
    [all, query, filter],
  );

  const handleSave = (item: FeatureItem, value: FeatureValue) => {
    if (!item.write_path || !item.field) return;
    save.mutate(
      { key: item.key, writePath: item.write_path, field: item.field, value },
      {
        onSuccess: () => setAnnouncement(describeSave(item, value)),
        onError: (e) => {
          const message = (e as Error).message;
          push({ kind: "error", text: `${item.label}: ${message}` });
          setAnnouncement(`${item.label} could not be saved. ${message}`);
        },
      },
    );
  };

  if (isLoading) {
    return (
      <SettingsSection title="Features" description="Everything you can switch on or off.">
        <SkeletonRows rows={8} />
      </SettingsSection>
    );
  }

  if (isError || !data) {
    return (
      <SettingsSection title="Features" description="Everything you can switch on or off.">
        <EmptyState
          title="Couldn't load the feature list"
          body={error instanceof Error ? error.message : "The features endpoint did not respond."}
        />
      </SettingsSection>
    );
  }

  const pendingKey = save.isPending ? save.variables?.key : undefined;

  return (
    <SettingsSection
      title="Features"
      description="Every capability in the app, what it costs, and where it is set."
    >
      <p className="ledger-surface px-4 py-3 text-[13px] text-ink-300">
        Everything ships switched <strong className="text-ink-100">on</strong>: nothing here is
        hidden behind a config file, and no capability is waiting for you to discover it. Turn
        off what you do not want. Rows marked with a money badge bill a provider when they run;
        rows that are set on individual profiles, schedules or triggers link to where they live
        instead of pretending to be one global switch.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={searchId} className="text-[12px] text-ink-300">
          Search features
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          placeholder="failover, retention, investigate…"
          onChange={(e) => setQuery(e.target.value)}
          className="ledger-input w-64 py-1.5 text-[12px]"
        />
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={[
                "ledger-pill transition-colors",
                filter === f.id ? "border-copper-500/60 text-copper-200" : "hover:text-ink-100",
              ].join(" ")}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p role="status" aria-live="polite" className="text-[12px] text-ink-400 tabular-nums">
          {shown.length} of {all.length} shown
        </p>
      </div>

      {/* One page-level announcer for saves. Ninety live regions would itself be a defect. */}
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title="No features match"
          body="Clear the search box or pick a different filter."
        />
      ) : (
        <div className="space-y-8">
          {[...data.groups]
            .sort((a, b) => a.order - b.order)
            .map((group) => {
              const items = shown.filter((i) => i.group === group.key);
              if (items.length === 0) return null;
              return (
                <FeatureGroup
                  key={group.key}
                  group={group}
                  items={items}
                  pendingKey={pendingKey}
                  unmetRequires={unmetRequires}
                  onSave={handleSave}
                />
              );
            })}
        </div>
      )}
    </SettingsSection>
  );
}
