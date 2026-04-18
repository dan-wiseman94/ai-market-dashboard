import { useState } from "react";
import { useProviderConfigs, useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { useAiUsage } from "@/hooks/useAiUsage";

const PROVIDERS = ["claude", "openai", "local"] as const;
type Provider = typeof PROVIDERS[number];

const DEFAULT_MODEL: Record<Provider, string> = {
  claude: "claude-sonnet-4-6",
  openai: "gpt-5",
  local: "",
};

type Draft = {
  api_key_write?: string;
  default_model?: string;
  daily_cost_cap_usd?: string;
  monthly_cost_cap_usd?: string;
  base_url?: string;
};

export default function ProviderConfigCard() {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const upsert = useUpsertProviderConfig();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});

  return (
    <div className="p-4 rounded border border-slate-800 space-y-4">
      <h2 className="text-lg font-medium">AI providers</h2>
      {PROVIDERS.map((p) => {
        const cfg = configs?.find((c) => c.provider === p);
        const draft = drafts[p] ?? {};
        const spent = usage?.today[p] ?? "0";
        return (
          <div key={p} className="border-t border-slate-800 pt-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium capitalize">{p}</span>
                <span className="ml-2 text-xs text-slate-500">
                  {cfg?.api_key_present ? "key: ●●●●" : "no key"}
                </span>
              </div>
              <div className="text-xs text-slate-400">today: ${Number(spent).toFixed(4)}</div>
            </div>
            <form
              className="mt-2 grid grid-cols-2 gap-2 text-sm"
              onSubmit={(e) => {
                e.preventDefault();
                const monthlyRaw = draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? "";
                upsert.mutate({ provider: p, body: {
                  api_key_write: draft.api_key_write ?? "",
                  default_model: draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[p],
                  daily_cost_cap_usd: draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00",
                  monthly_cost_cap_usd: monthlyRaw === "" ? null : monthlyRaw,
                  base_url: draft.base_url ?? cfg?.base_url ?? "",
                } }, { onSuccess: () => setDrafts((d) => ({ ...d, [p]: {} })) });
              }}
            >
              <input
                placeholder="API key (leave blank to keep)"
                type="password"
                value={draft.api_key_write ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, api_key_write: e.target.value } }))}
                className="col-span-2 px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              <input
                placeholder={`Default model (${DEFAULT_MODEL[p]})`}
                value={draft.default_model ?? cfg?.default_model ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, default_model: e.target.value } }))}
                className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              <input
                placeholder="Daily cap USD"
                value={draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00"}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, daily_cost_cap_usd: e.target.value } }))}
                className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              <input
                placeholder="Monthly cap USD (blank = none)"
                value={draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, monthly_cost_cap_usd: e.target.value } }))}
                className="col-span-2 px-2 py-1 rounded bg-slate-900 border border-slate-700"
              />
              {p === "local" && (
                <input
                  placeholder="Base URL (e.g. http://host.docker.internal:11434/v1)"
                  value={draft.base_url ?? cfg?.base_url ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [p]: { ...draft, base_url: e.target.value } }))}
                  className="col-span-2 px-2 py-1 rounded bg-slate-900 border border-slate-700"
                />
              )}
              <button className="col-span-2 px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">
                Save
              </button>
            </form>
          </div>
        );
      })}
    </div>
  );
}
