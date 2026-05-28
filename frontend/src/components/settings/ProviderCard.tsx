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

export default function ProviderCard({ provider }: { provider: ProviderId }) {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const { data: caps } = useCostsCaps();
  const upsert = useUpsertProviderConfig();
  const probe = useProbeProvider();
  const { push } = useToast();
  const [draft, setDraft] = useState<Draft>({});
  const [probeMsg, setProbeMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const isLocal = provider === "local";
  const cfg = configs?.find((c) => c.provider === provider);
  const capRow = caps?.find((r) => r.provider === provider);
  const spent = usage?.today?.[provider] ?? "0";
  const enabled = cfg?.enabled ?? true;

  const model = draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[provider];
  const daily = draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00";
  const monthly = draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? "";
  const baseUrl = draft.base_url ?? cfg?.base_url ?? "";
  const apiKey = draft.api_key_write ?? "";
  const discovered = cfg?.discovered_models ?? [];

  const dailyNum = Number(daily);
  const monthlyNum = monthly === "" ? null : Number(monthly);
  const dailyInvalid = daily.trim() === "" || Number.isNaN(dailyNum) || dailyNum < 0;
  const monthlyInvalid = monthly !== "" && (Number.isNaN(monthlyNum as number) || (monthlyNum as number) < 0);
  const modelInvalid = model.trim() === "";
  const baseUrlInvalid = isLocal && baseUrl.trim() === "";
  const invalid = isLocal
    ? modelInvalid || baseUrlInvalid
    : dailyInvalid || monthlyInvalid || modelInvalid;

  const set = (patch: Draft) => setDraft((d) => ({ ...d, ...patch }));

  // Populate the local model list once when we have an endpoint but no models yet.
  // Auto-probe is silent (no status message); only the explicit button surfaces errors.
  const autoProbed = useRef(false);
  useEffect(() => {
    if (isLocal && !autoProbed.current && baseUrl.trim() !== "" && discovered.length === 0) {
      autoProbed.current = true;
      probe.mutate({ provider, body: {} });
    }
  }, [isLocal, baseUrl, discovered.length, provider, probe]);

  const runProbe = () => {
    if (baseUrlInvalid) return;
    setProbeMsg(null);
    probe.mutate(
      { provider, body: { base_url: baseUrl, api_key_write: apiKey || undefined } },
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
    if (invalid) return;
    const body: Partial<ProviderConfig> & { api_key_write?: string } = isLocal
      ? { default_model: model, base_url: baseUrl }
      : {
          default_model: model,
          daily_cost_cap_usd: daily,
          monthly_cost_cap_usd: monthly === "" ? null : monthly,
        };
    if (apiKey) body.api_key_write = apiKey; // omit when blank → serializer keeps the stored key
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
          <Toggle checked={enabled} onChange={toggleEnabled} label={`${LABEL[provider]} enabled`} disabled={upsert.isPending} />
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field
            label={`${LABEL[provider]} API key`}
            hint={cfg?.api_key_present ? "A key is stored. Paste to replace; leave blank to keep." : isLocal ? "Optional — most local servers ignore it." : "Paste your API key."}
          >
            {({ id, describedBy }) => (
              <input
                id={id} aria-describedby={describedBy} type="password" value={apiKey}
                placeholder={cfg?.api_key_present ? "•••••••• (unchanged)" : "sk-…"}
                onChange={(e) => set({ api_key_write: e.target.value })}
                className="ledger-input w-full py-2 font-mono text-[12px]"
              />
            )}
          </Field>
        </div>

        {isLocal && (
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
                    onChange={(e) => set({ base_url: e.target.value })}
                    className="ledger-input w-full py-2 font-mono text-[12px]"
                  />
                  <div className="flex items-center gap-3">
                    <button
                      type="button" className="ledger-cta"
                      onClick={runProbe}
                      disabled={baseUrlInvalid || probe.isPending}
                    >
                      {probe.isPending ? "Testing…" : "Test connection"}
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
        )}

        <Field
          label="Default model"
          hint={isLocal && discovered.length === 0 ? "Test the connection to list available models." : undefined}
          error={modelInvalid ? "Pick or enter a model." : undefined}
        >
          {({ id, describedBy }) => (
            <ModelSelect provider={provider} value={model} id={id} describedBy={describedBy}
              models={isLocal ? discovered : undefined}
              onChange={(m) => set({ default_model: m })} />
          )}
        </Field>

        {!isLocal && (
          <>
            <Field label="Daily cap (USD)" hint="Hard stop — runs blocked past this."
                   error={dailyInvalid ? "Enter a non-negative number." : undefined}>
              {({ id, describedBy }) => (
                <input id={id} aria-describedby={describedBy} inputMode="decimal" value={daily}
                  onChange={(e) => set({ daily_cost_cap_usd: e.target.value })}
                  className="ledger-input w-full py-2 tabular-nums" />
              )}
            </Field>

            <Field label="Monthly cap (USD)" hint="Blank = no monthly limit."
                   error={monthlyInvalid ? "Enter a non-negative number or leave blank." : undefined}>
              {({ id, describedBy }) => (
                <input id={id} aria-describedby={describedBy} inputMode="decimal" value={monthly} placeholder="none"
                  onChange={(e) => set({ monthly_cost_cap_usd: e.target.value })}
                  className="ledger-input w-full py-2 tabular-nums" />
              )}
            </Field>
          </>
        )}
      </div>

      {isLocal ? (
        <p className="mt-5 border-t border-rule-soft pt-4 text-[11px] text-ink-400">
          Runs on your machine — no API cost.
        </p>
      ) : (
        capRow && (
          <div className="mt-5 space-y-2 border-t border-rule-soft pt-4">
            <CapMeter label="Daily" cap={capRow.daily.cap} spent={capRow.daily.spent} pct={capRow.daily.pct} />
            {capRow.monthly && (
              <CapMeter label="Monthly" cap={capRow.monthly.cap} spent={capRow.monthly.spent} pct={capRow.monthly.pct} />
            )}
          </div>
        )
      )}

      <div className="mt-5">
        <button type="button" className="ledger-cta" onClick={save} disabled={upsert.isPending || invalid}>
          {upsert.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
