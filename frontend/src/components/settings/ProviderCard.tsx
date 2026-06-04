import { useEffect, useRef, useState } from "react";
import { useProviderConfigs, useUpsertProviderConfig, useProbeProvider } from "@/hooks/useProviderConfigs";
import { useAiUsage } from "@/hooks/useAiUsage";
import { useCostsCaps } from "@/hooks/useCosts";
import { useToast } from "@/hooks/useToast";
import type { ProviderConfig } from "@/api/ai";
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import ModelSelect from "@/components/settings/ModelSelect";
import CapMeter from "@/components/settings/CapMeter";

type ProviderId = "claude" | "openai" | "local";
const LABEL: Record<ProviderId, string> = { claude: "Claude", openai: "OpenAI", local: "Local" };
const DEFAULT_MODEL: Record<ProviderId, string> = {
  claude: "claude-sonnet-4-6", openai: "gpt-5", local: "",
};

type Draft = {
  api_key_write?: string;
  default_model?: string;
  daily_cost_cap_usd?: string;
  monthly_cost_cap_usd?: string;
  base_url?: string;
};

type ProbeMsg = { ok: boolean; text: string } | null;

type CapRow = NonNullable<ReturnType<typeof useCostsCaps>["data"]>[number];

/** Derived values + validation flags for the current draft over the stored config. */
type DerivedState = {
  isLocal: boolean;
  cfg: ProviderConfig | undefined;
  capRow: CapRow | undefined;
  spent: string;
  enabled: boolean;
  model: string;
  daily: string;
  monthly: string;
  baseUrl: string;
  apiKey: string;
  discovered: string[];
  dailyInvalid: boolean;
  monthlyInvalid: boolean;
  modelInvalid: boolean;
  baseUrlInvalid: boolean;
  invalid: boolean;
};

/** Resolved field values: draft override → stored config → built-in default. */
type ResolvedFields = {
  model: string;
  daily: string;
  monthly: string;
  baseUrl: string;
  apiKey: string;
  discovered: string[];
};

function resolveCaps(draft: Draft, cfg: ProviderConfig | undefined): { daily: string; monthly: string } {
  return {
    daily: draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00",
    monthly: draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? "",
  };
}

function resolveFields(provider: ProviderId, draft: Draft, cfg: ProviderConfig | undefined): ResolvedFields {
  return {
    model: draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[provider],
    baseUrl: draft.base_url ?? cfg?.base_url ?? "",
    apiKey: draft.api_key_write ?? "",
    discovered: cfg?.discovered_models ?? [],
    ...resolveCaps(draft, cfg),
  };
}

type ValidationFlags = {
  dailyInvalid: boolean;
  monthlyInvalid: boolean;
  modelInvalid: boolean;
  baseUrlInvalid: boolean;
  invalid: boolean;
};

function validate(isLocal: boolean, f: ResolvedFields): ValidationFlags {
  const dailyNum = Number(f.daily);
  const monthlyNum = f.monthly === "" ? null : Number(f.monthly);
  const dailyInvalid = f.daily.trim() === "" || Number.isNaN(dailyNum) || dailyNum < 0;
  const monthlyInvalid = f.monthly !== "" && (Number.isNaN(monthlyNum as number) || (monthlyNum as number) < 0);
  const modelInvalid = f.model.trim() === "";
  const baseUrlInvalid = isLocal && f.baseUrl.trim() === "";
  const invalid = isLocal
    ? modelInvalid || baseUrlInvalid
    : dailyInvalid || monthlyInvalid || modelInvalid;
  return { dailyInvalid, monthlyInvalid, modelInvalid, baseUrlInvalid, invalid };
}

function deriveState(
  provider: ProviderId,
  draft: Draft,
  configs: ProviderConfig[] | undefined,
  caps: CapRow[] | undefined,
  usage: ReturnType<typeof useAiUsage>["data"],
): DerivedState {
  const isLocal = provider === "local";
  const cfg = configs?.find((c) => c.provider === provider);
  const capRow = caps?.find((r) => r.provider === provider);
  const spent = usage?.today?.[provider] ?? "0";
  const enabled = cfg?.enabled ?? true;

  const fields = resolveFields(provider, draft, cfg);
  const flags = validate(isLocal, fields);

  return { isLocal, cfg, capRow, spent, enabled, ...fields, ...flags };
}

type SetDraft = (patch: Draft) => void;

function CardHeader({
  provider, enabled, cfg, isLocal, spent, onToggle, togglePending,
}: {
  provider: ProviderId;
  enabled: boolean;
  cfg: ProviderConfig | undefined;
  isLocal: boolean;
  spent: string;
  onToggle: (next: boolean) => void;
  togglePending: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className={`inline-block h-2 w-2 rounded-full ${enabled ? "bg-copper-400" : "bg-ink-600"}`} aria-hidden />
        <h3 className="font-display text-[1.05rem] text-ink-50">{LABEL[provider]}</h3>
        <span className="ledger-pill" data-tone={cfg?.api_key_present ? "copper" : undefined}>
          {cfg?.api_key_present ? "key set ••••" : "no key"}
        </span>
      </div>
      <div className="flex items-center gap-4">
        {!isLocal && (
          <span className="font-mono text-[11px] text-ink-400 tabular-nums">today ${Number(spent).toFixed(4)}</span>
        )}
        <Toggle checked={enabled} onChange={onToggle} label={`${LABEL[provider]} enabled`} disabled={togglePending} />
      </div>
    </div>
  );
}

function ApiKeyField({
  provider, cfg, isLocal, apiKey, setDraft,
}: {
  provider: ProviderId;
  cfg: ProviderConfig | undefined;
  isLocal: boolean;
  apiKey: string;
  setDraft: SetDraft;
}) {
  return (
    <div className="sm:col-span-2">
      <Field
        label={`${LABEL[provider]} API key`}
        hint={cfg?.api_key_present ? "A key is stored. Paste to replace; leave blank to keep." : isLocal ? "Optional — most local servers ignore it." : "Paste your API key."}
      >
        {({ id, describedBy }) => (
          <input
            id={id} aria-describedby={describedBy} type="password" value={apiKey}
            placeholder={cfg?.api_key_present ? "•••••••• (unchanged)" : "sk-…"}
            onChange={(e) => setDraft({ api_key_write: e.target.value })}
            className="ledger-input w-full py-2 font-mono text-[12px]"
          />
        )}
      </Field>
    </div>
  );
}

function LocalBaseUrlField({
  baseUrl, baseUrlInvalid, probeMsg, probePending, onProbe, setDraft,
}: {
  baseUrl: string;
  baseUrlInvalid: boolean;
  probeMsg: ProbeMsg;
  probePending: boolean;
  onProbe: () => void;
  setDraft: SetDraft;
}) {
  return (
    <div className="sm:col-span-2">
      <Field
        label="Base URL"
        hint="Your OpenAI-compatible server (Ollama, LM Studio, vLLM). On Linux: http://host.docker.internal:<port>/v1"
        error={baseUrlInvalid ? "Base URL is required for local." : undefined}
      >
        {({ id, describedBy }) => (
          <div className="space-y-2">
            <input
              id={id} aria-describedby={describedBy} value={baseUrl} aria-required="true"
              placeholder="http://host.docker.internal:11434/v1"
              onChange={(e) => setDraft({ base_url: e.target.value })}
              className="ledger-input w-full py-2 font-mono text-[12px]"
            />
            <div className="flex items-center gap-3">
              <button
                type="button" className="ledger-cta"
                onClick={onProbe}
                disabled={baseUrlInvalid || probePending}
              >
                {probePending ? "Testing…" : "Test connection"}
              </button>
              {probeMsg && (
                <span className={`text-[12px] ${probeMsg.ok ? "text-copper-300" : "text-loss"}`}>
                  {probeMsg.text}
                </span>
              )}
            </div>
          </div>
        )}
      </Field>
    </div>
  );
}

function ModelField({
  provider, isLocal, model, modelInvalid, discovered, setDraft,
}: {
  provider: ProviderId;
  isLocal: boolean;
  model: string;
  modelInvalid: boolean;
  discovered: string[];
  setDraft: SetDraft;
}) {
  return (
    <Field
      label="Default model"
      hint={isLocal && discovered.length === 0 ? "Test the connection to list available models." : undefined}
      error={modelInvalid ? "Pick or enter a model." : undefined}
    >
      {({ id, describedBy }) => (
        <ModelSelect provider={provider} value={model} id={id} describedBy={describedBy}
          models={isLocal ? discovered : undefined}
          onChange={(m) => setDraft({ default_model: m })} />
      )}
    </Field>
  );
}

function CostCapFields({
  daily, monthly, dailyInvalid, monthlyInvalid, setDraft,
}: {
  daily: string;
  monthly: string;
  dailyInvalid: boolean;
  monthlyInvalid: boolean;
  setDraft: SetDraft;
}) {
  return (
    <>
      <Field label="Daily cap (USD)" hint="Hard stop — runs blocked past this."
             error={dailyInvalid ? "Enter a non-negative number." : undefined}>
        {({ id, describedBy }) => (
          <input id={id} aria-describedby={describedBy} inputMode="decimal" value={daily}
            onChange={(e) => setDraft({ daily_cost_cap_usd: e.target.value })}
            className="ledger-input w-full py-2 tabular-nums" />
        )}
      </Field>

      <Field label="Monthly cap (USD)" hint="Blank = no monthly limit."
             error={monthlyInvalid ? "Enter a non-negative number or leave blank." : undefined}>
        {({ id, describedBy }) => (
          <input id={id} aria-describedby={describedBy} inputMode="decimal" value={monthly} placeholder="none"
            onChange={(e) => setDraft({ monthly_cost_cap_usd: e.target.value })}
            className="ledger-input w-full py-2 tabular-nums" />
        )}
      </Field>
    </>
  );
}

function CardFooter({ isLocal, capRow }: { isLocal: boolean; capRow: CapRow | undefined }) {
  if (isLocal) {
    return (
      <p className="mt-5 border-t border-rule-soft pt-4 text-[11px] text-ink-400">
        Runs on your machine — no API cost.
      </p>
    );
  }
  if (!capRow) return null;
  return (
    <div className="mt-5 space-y-2 border-t border-rule-soft pt-4">
      <CapMeter label="Daily" cap={capRow.daily.cap} spent={capRow.daily.spent} pct={capRow.daily.pct} />
      {capRow.monthly && (
        <CapMeter label="Monthly" cap={capRow.monthly.cap} spent={capRow.monthly.spent} pct={capRow.monthly.pct} />
      )}
    </div>
  );
}

export default function ProviderCard({ provider }: { provider: ProviderId }) {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const { data: caps } = useCostsCaps();
  const upsert = useUpsertProviderConfig();
  const probe = useProbeProvider();
  const { push } = useToast();
  const [draft, setDraft] = useState<Draft>({});
  const [probeMsg, setProbeMsg] = useState<ProbeMsg>(null);

  const d = deriveState(provider, draft, configs, caps, usage);
  const set: SetDraft = (patch) => setDraft((prev) => ({ ...prev, ...patch }));

  // Populate the local model list once when we have an endpoint but no models yet.
  // Auto-probe is silent (no status message); only the explicit button surfaces errors.
  const autoProbed = useRef(false);
  useEffect(() => {
    if (d.isLocal && !autoProbed.current && d.baseUrl.trim() !== "" && d.discovered.length === 0) {
      autoProbed.current = true;
      probe.mutate({ provider, body: {} });
    }
  }, [d.isLocal, d.baseUrl, d.discovered.length, provider, probe]);

  const runProbe = () => {
    if (d.baseUrlInvalid) return;
    setProbeMsg(null);
    probe.mutate(
      { provider, body: { base_url: d.baseUrl, api_key_write: d.apiKey || undefined } },
      {
        onSuccess: (res) => {
          setProbeMsg(
            res.ok
              ? { ok: true, text: `Connected — ${(res.models ?? []).length} models found.` }
              : { ok: false, text: res.error ?? "Connection failed." },
          );
        },
        onError: (e) => setProbeMsg({ ok: false, text: (e as Error).message }),
      },
    );
  };

  const toggleEnabled = (next: boolean) => {
    upsert.mutate(
      { provider, body: { enabled: next } },
      {
        onSuccess: () => push({ kind: "info", text: `${LABEL[provider]} ${next ? "enabled" : "disabled"}.` }),
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  const save = () => {
    if (d.invalid) return;
    const body: Partial<ProviderConfig> & { api_key_write?: string } = d.isLocal
      ? { default_model: d.model, base_url: d.baseUrl }
      : {
          default_model: d.model,
          daily_cost_cap_usd: d.daily,
          monthly_cost_cap_usd: d.monthly === "" ? null : d.monthly,
        };
    if (d.apiKey) body.api_key_write = d.apiKey; // omit when blank → serializer keeps the stored key
    upsert.mutate(
      { provider, body },
      {
        onSuccess: () => { setDraft({}); push({ kind: "success", text: `${LABEL[provider]} settings saved.` }); },
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  return (
    <div className="ledger-surface p-5" data-testid={`provider-card-${provider}`}>
      <CardHeader
        provider={provider} enabled={d.enabled} cfg={d.cfg} isLocal={d.isLocal}
        spent={d.spent} onToggle={toggleEnabled} togglePending={upsert.isPending}
      />

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <ApiKeyField provider={provider} cfg={d.cfg} isLocal={d.isLocal} apiKey={d.apiKey} setDraft={set} />

        {d.isLocal && (
          <LocalBaseUrlField
            baseUrl={d.baseUrl} baseUrlInvalid={d.baseUrlInvalid} probeMsg={probeMsg}
            probePending={probe.isPending} onProbe={runProbe} setDraft={set}
          />
        )}

        <ModelField
          provider={provider} isLocal={d.isLocal} model={d.model} modelInvalid={d.modelInvalid}
          discovered={d.discovered} setDraft={set}
        />

        {!d.isLocal && (
          <CostCapFields
            daily={d.daily} monthly={d.monthly} dailyInvalid={d.dailyInvalid}
            monthlyInvalid={d.monthlyInvalid} setDraft={set}
          />
        )}
      </div>

      <CardFooter isLocal={d.isLocal} capRow={d.capRow} />

      <div className="mt-5">
        <button type="button" className="ledger-cta" onClick={save} disabled={upsert.isPending || d.invalid}>
          {upsert.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
