import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { FeatureItem, FeatureValue } from "@/api/features";
import {
  BADGE_ALWAYS_ON,
  BADGE_ENV_ONLY,
  BADGE_MONEY,
  BADGE_RETROACTIVE,
  SOURCE_LABELS,
  deepLinkLabel,
  moneyConfirm,
  retroactiveConfirm,
} from "@/lib/featureGroups";

type Props = {
  item: FeatureItem;
  /** True only for the row currently being written, so one save never freezes the page. */
  pending?: boolean;
  /** Labels of rows this one depends on that are currently off. */
  unmetRequires?: string[];
  onSave: (value: FeatureValue) => void;
};

function defaultLabel(item: FeatureItem): string {
  if (item.kind === "toggle") return item.default_value ? "on" : "off";
  if (item.kind === "number") {
    return item.unit ? `${item.default_value} ${item.unit}` : String(item.default_value);
  }
  if (item.kind === "text") return item.default_value || "none";
  return "";
}

/**
 * One switchable capability.
 *
 * Every word the user reads comes from the payload; this file contains no feature
 * name. The three provenance states are a badge plus a reset affordance rather than a
 * third switch position — a tri-state control has no ARIA semantics and would force
 * the user to learn that NULL means "inherit" just to turn something off.
 */
export default function FeatureRow({ item, pending = false, unmetRequires = [], onSave }: Props) {
  const uid = useId();
  const labelId = `${uid}-label`;
  const descId = `${uid}-desc`;
  const metaId = `${uid}-meta`;

  const requirement = item.requirement;
  const blocked = requirement !== null && requirement.satisfied === false;
  const disabled = pending || blocked || !item.editable;

  const describedBy = [descId, metaId].join(" ");

  const confirmOn = (next: boolean): boolean => {
    if (!next) return true; // turning something off is always free
    if (item.retroactive) return window.confirm(retroactiveConfirm(item.label));
    if (item.costs_money) return window.confirm(moneyConfirm(item.label, item.cost_note));
    return true;
  };

  return (
    <div className="ledger-surface px-4 py-3" data-testid={`feature-row-${item.key}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span id={labelId} className="text-[13px] font-medium text-ink-100">
              {item.label}
            </span>
            <Badges item={item} />
          </div>
          <p id={descId} className="mt-0.5 text-[12px] text-ink-400">
            {item.summary}
          </p>
        </div>
        <div className="shrink-0 pt-0.5">
          <Control
            item={item}
            labelId={labelId}
            describedBy={describedBy}
            disabled={disabled}
            confirmOn={confirmOn}
            onSave={onSave}
          />
        </div>
      </div>

      <RowMeta
        item={item}
        metaId={metaId}
        blocked={blocked}
        pending={pending}
        unmetRequires={unmetRequires}
        onSave={onSave}
      />

      <details className="mt-1.5">
        <summary className="cursor-pointer text-[11px] text-ink-400 hover:text-ink-200">
          What this does
        </summary>
        <p className="mt-1 max-w-2xl whitespace-pre-line text-[12px] text-ink-300">{item.help}</p>
        {item.costs_money && item.cost_note && (
          <p className="mt-1 max-w-2xl text-[12px] text-copper-300">{item.cost_note}</p>
        )}
      </details>
    </div>
  );
}

/**
 * The line under the control: provenance, then every reason this row might not do
 * what its switch suggests. Each reason is visible text inside the row's
 * aria-describedby target — never a `title` attribute, which keyboard users never see.
 */
function RowMeta({
  item,
  metaId,
  blocked,
  pending,
  unmetRequires,
  onSave,
}: {
  item: FeatureItem;
  metaId: string;
  blocked: boolean;
  pending: boolean;
  unmetRequires: string[];
  onSave: (value: FeatureValue) => void;
}) {
  const requirement = item.requirement;
  return (
    <div id={metaId} className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
      <Provenance item={item} onSave={onSave} pending={pending} />
      {blocked && requirement && (
        <Link to={requirement.manage_path} className="text-copper-300 underline underline-offset-2">
          Connect {requirement.label} first →
        </Link>
      )}
      {requirement?.satisfied === null && (
        <span className="text-ink-400">{requirement.label} connection status unavailable.</span>
      )}
      {item.provider_only && (
        <span className="text-ink-400">
          Has no effect on other providers; a run warns and continues.
        </span>
      )}
      {unmetRequires.length > 0 && (
        <span className="text-ink-400">
          Inert while {unmetRequires.join(" and ")} {unmetRequires.length > 1 ? "are" : "is"} off.
        </span>
      )}
      {!item.editable && item.env_only_reason && (
        <span className="text-ink-400">{item.env_only_reason}</span>
      )}
    </div>
  );
}


function Badges({ item }: { item: FeatureItem }) {
  return (
    <>
      {item.costs_money && (
        <span className="ledger-pill" data-tone="copper">
          {BADGE_MONEY}
        </span>
      )}
      {item.retroactive && (
        <span className="ledger-pill" data-tone="loss">
          {BADGE_RETROACTIVE}
        </span>
      )}
      {item.provider_only && <span className="ledger-pill">{item.provider_only} only</span>}
      {item.backing === "env_only" && <span className="ledger-pill">{BADGE_ENV_ONLY}</span>}
      {item.backing === "informational" && <span className="ledger-pill">{BADGE_ALWAYS_ON}</span>}
    </>
  );
}

function Provenance({
  item,
  onSave,
  pending,
}: {
  item: FeatureItem;
  onSave: (value: FeatureValue) => void;
  pending: boolean;
}) {
  if (item.kind === "per_object") {
    return (
      <span className="text-ink-400">Set per {item.noun.replace(/s$/, "")}, not globally.</span>
    );
  }
  const tone = item.source === "default" ? undefined : "copper";
  // Only a SystemSettings-backed row has a nullable override column to clear. The
  // briefing singleton's columns are NOT NULL, so offering a reset there would 400.
  const resettable =
    item.editable && item.backing === "system_settings" && item.source === "override";
  return (
    <>
      <span className="ledger-pill" data-tone={tone}>
        {SOURCE_LABELS[item.source] ?? item.source}
      </span>
      {resettable && (
        <button
          type="button"
          disabled={pending}
          onClick={() => onSave(null)}
          className="text-copper-300 underline underline-offset-2 disabled:opacity-50"
        >
          Reset to default ({defaultLabel(item)})
        </button>
      )}
      {!resettable && item.source !== "override" && (
        <span className="text-ink-400">Default: {defaultLabel(item)}</span>
      )}
    </>
  );
}

type ControlProps = {
  item: FeatureItem;
  labelId: string;
  describedBy: string;
  disabled: boolean;
  confirmOn: (next: boolean) => boolean;
  onSave: (value: FeatureValue) => void;
};

function Control({ item, labelId, describedBy, disabled, confirmOn, onSave }: ControlProps) {
  if (item.kind === "per_object") return <Rollup item={item} />;
  if (!item.editable) return <ReadOnlyValue item={item} />;
  if (item.kind === "toggle") {
    return (
      <Switch
        checked={item.value}
        labelId={labelId}
        describedBy={describedBy}
        disabled={disabled}
        onChange={(next) => {
          if (confirmOn(next)) onSave(next);
        }}
      />
    );
  }
  if (item.kind === "number") {
    return (
      <NumberInput item={item} labelId={labelId} describedBy={describedBy} disabled={disabled} onSave={onSave} />
    );
  }
  return (
    <TextInput item={item} labelId={labelId} describedBy={describedBy} disabled={disabled} onSave={onSave} />
  );
}

function Switch({
  checked,
  labelId,
  describedBy,
  disabled,
  onChange,
}: {
  checked: boolean;
  labelId: string;
  describedBy: string;
  disabled: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelId}
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

/**
 * Numbers commit on blur and on Enter, never per keystroke: typing "400" would
 * otherwise PATCH 4, then 40, and the server-side floors reject the intermediates
 * mid-keystroke.
 */
function NumberInput({
  item,
  labelId,
  describedBy,
  disabled,
  onSave,
}: {
  item: Extract<FeatureItem, { kind: "number" }>;
  labelId: string;
  describedBy: string;
  disabled: boolean;
  onSave: (value: FeatureValue) => void;
}) {
  const [draft, setDraft] = useState(String(item.value));
  const commit = () => {
    const next = Number(draft);
    if (draft.trim() === "" || Number.isNaN(next) || next === item.value) {
      setDraft(String(item.value));
      return;
    }
    onSave(next);
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        type="number"
        inputMode="decimal"
        step={item.is_float ? 0.01 : 1}
        min={item.min_value ?? undefined}
        max={item.max_value ?? undefined}
        value={draft}
        disabled={disabled}
        aria-labelledby={labelId}
        aria-describedby={describedBy}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
        }}
        className="ledger-input w-28 py-1 text-right tabular-nums"
      />
      {item.unit && <span className="text-[11px] text-ink-400">{item.unit}</span>}
    </span>
  );
}

function TextInput({
  item,
  labelId,
  describedBy,
  disabled,
  onSave,
}: {
  item: Extract<FeatureItem, { kind: "text" }>;
  labelId: string;
  describedBy: string;
  disabled: boolean;
  onSave: (value: FeatureValue) => void;
}) {
  const [draft, setDraft] = useState(item.value);
  if (item.choices.length > 0) {
    return (
      <select
        value={item.value}
        disabled={disabled}
        aria-labelledby={labelId}
        aria-describedby={describedBy}
        onChange={(e) => onSave(e.target.value)}
        className="ledger-input w-48 py-1 text-[12px]"
      >
        {item.choices.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    );
  }
  const commit = () => {
    if (draft !== item.value) onSave(draft);
  };
  return (
    <input
      type="text"
      value={draft}
      disabled={disabled}
      maxLength={item.max_length || undefined}
      aria-labelledby={labelId}
      aria-describedby={describedBy}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
      }}
      className="ledger-input w-48 py-1 font-mono text-[12px]"
    />
  );
}

function ReadOnlyValue({ item }: { item: Exclude<FeatureItem, { kind: "per_object" }> }) {
  const shown =
    item.kind === "toggle" ? (item.value ? "on" : "off") : `${item.value}${item.kind === "number" && item.unit ? ` ${item.unit}` : ""}`;
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span className="ledger-pill">{shown || "—"}</span>
      {item.env_var && <code className="font-mono text-[10px] text-ink-400">{item.env_var}</code>}
    </span>
  );
}

/**
 * A per-object row shows how many rows have it on and links to where they live. It
 * deliberately renders no switch: a disabled switch reports aria-checked="false",
 * which states "this is off" — wrong when four of thirteen profiles have it on.
 */
function Rollup({ item }: { item: Extract<FeatureItem, { kind: "per_object" }> }) {
  const label = item.deep_link ? deepLinkLabel(item.deep_link) : "";
  return (
    <span className="inline-flex flex-col items-end gap-1 text-right">
      {item.degraded || item.total === null ? (
        <span className="text-[11px] text-ink-400">Count unavailable</span>
      ) : item.on === null ? (
        <span className="text-[11px] text-ink-300 tabular-nums">
          {item.total} {item.total === 1 ? item.noun.replace(/s$/, "") : item.noun}
        </span>
      ) : (
        <span className="text-[11px] text-ink-300 tabular-nums">
          On for {item.on} of {item.total} {item.noun}
        </span>
      )}
      {item.deep_link ? (
        <Link
          to={item.deep_link}
          aria-label={`Manage ${item.label} in ${label}`}
          className="text-[11px] text-copper-300 underline underline-offset-2"
        >
          {label} →
        </Link>
      ) : (
        <span className="text-[11px] text-ink-400">No page yet — API only</span>
      )}
    </span>
  );
}
