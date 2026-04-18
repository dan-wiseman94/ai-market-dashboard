import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Condition, type EventTrigger,
  createTrigger, evaluateTrigger, fetchTriggers, updateTrigger,
  backtestTrigger, type BacktestMatch,
} from "@/api/triggers";
import RuleBuilder from "@/components/triggers/RuleBuilder";
import FiringsTable from "@/components/triggers/FiringsTable";
import { apiGet } from "@/api/client";

type Profile = { id: number; name: string };

const EMPTY: Pick<EventTrigger, "name" | "condition" | "cooldown_seconds" | "enabled"> = {
  name: "",
  condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] },
  cooldown_seconds: 1800,
  enabled: true,
};

function useDebounced<T>(value: T, ms: number): T {
  const [deb, setDeb] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDeb(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return deb;
}

export default function TriggerEditorPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const isNew = !rawId || rawId === "new";
  const id = isNew ? null : Number(rawId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const profilesQ = useQuery({
    queryKey: ["profiles"],
    queryFn: () => apiGet<Profile[]>("/api/profiles/"),
  });

  const triggersQ = useQuery({
    queryKey: ["triggers"],
    queryFn: fetchTriggers,
    enabled: !isNew,
  });

  const existing = triggersQ.data?.find((t) => t.id === id);
  const [form, setForm] = useState(EMPTY);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [tab, setTab] = useState<"condition" | "firings" | "backtest">("condition");
  const ninetyAgo = new Date(Date.now() - 90 * 24 * 3600_000).toISOString().slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  const [btStart, setBtStart] = useState(ninetyAgo);
  const [btEnd, setBtEnd] = useState(today);
  const [btResult, setBtResult] = useState<{ match_count: number; matches: BacktestMatch[] } | null>(null);
  const backtest = useMutation({
    mutationFn: () =>
      backtestTrigger({
        condition: form.condition,
        start: new Date(btStart).toISOString(),
        end: new Date(btEnd + "T23:59:59").toISOString(),
      }),
    onSuccess: (data) => setBtResult(data),
  });

  useEffect(() => {
    if (existing) {
      setForm({
        name: existing.name,
        condition: existing.condition,
        cooldown_seconds: existing.cooldown_seconds,
        enabled: existing.enabled,
      });
      setProfileId(existing.profile);
    }
  }, [existing]);

  useEffect(() => {
    if (profilesQ.data && profileId === null && profilesQ.data.length > 0) {
      setProfileId(profilesQ.data[0].id);
    }
  }, [profilesQ.data, profileId]);

  const debounced = useDebounced(form.condition, 600);
  const previewQ = useQuery({
    queryKey: ["trigger-preview", debounced, profileId],
    queryFn: () => evaluateTrigger({ condition: debounced, profile: profileId ?? undefined }),
    enabled: profileId !== null,
    retry: false,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!profileId) throw new Error("profile required");
      const body = { ...form, profile: profileId };
      if (isNew) return createTrigger(body);
      return updateTrigger(id!, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["triggers"] });
      navigate("/triggers");
    },
  });

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold">
        {isNew ? "New trigger" : `Edit trigger: ${existing?.name ?? ""}`}
      </h1>

      {!isNew && (
        <div className="flex gap-4 border-b border-neutral-800 mb-4">
          <button
            type="button"
            className={`py-2 ${tab === "condition" ? "text-white border-b-2 border-indigo-500" : "text-neutral-400"}`}
            onClick={() => setTab("condition")}
          >Condition</button>
          <button
            type="button"
            className={`py-2 ${tab === "firings" ? "text-white border-b-2 border-indigo-500" : "text-neutral-400"}`}
            onClick={() => setTab("firings")}
          >Firings ({existing?.firings_count ?? 0})</button>
          <button
            type="button"
            className={`py-2 ${tab === "backtest" ? "text-white border-b-2 border-indigo-500" : "text-neutral-400"}`}
            onClick={() => setTab("backtest")}
          >Backtest</button>
        </div>
      )}

      {!isNew && tab === "firings" ? (
        <FiringsTable triggerId={id!} />
      ) : tab === "backtest" ? (
        <div className="space-y-3">
          <div className="text-sm text-neutral-400">
            Replay the current condition against stored OHLC bars. Only <code>price</code> and
            <code>pct_change</code> leaves evaluate; live-only metrics are skipped.
          </div>
          <div className="flex gap-3 items-end">
            <label className="text-sm">
              <div className="text-neutral-400 mb-1">Start</div>
              <input type="date" value={btStart} onChange={(e) => setBtStart(e.target.value)}
                     className="bg-neutral-800 px-3 py-2 rounded" />
            </label>
            <label className="text-sm">
              <div className="text-neutral-400 mb-1">End</div>
              <input type="date" value={btEnd} onChange={(e) => setBtEnd(e.target.value)}
                     className="bg-neutral-800 px-3 py-2 rounded" />
            </label>
            <button
              type="button"
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
              onClick={() => backtest.mutate()}
              disabled={backtest.isPending}
            >{backtest.isPending ? "Running…" : "Run backtest"}</button>
          </div>
          {backtest.isError && (
            <div className="text-rose-400 text-sm">
              {(backtest.error as Error)?.message ?? "Backtest failed"}
            </div>
          )}
          {btResult && (
            <div className="space-y-1">
              <div className="text-sm">
                <span className="font-mono">{btResult.match_count}</span>
                <span className="text-neutral-400"> matches</span>
              </div>
              <ul className="text-xs font-mono text-neutral-300 max-h-60 overflow-auto">
                {btResult.matches.slice(0, 50).map((m, i) => (
                  <li key={i}>
                    {new Date(m.ts).toLocaleDateString()} —
                    {Object.entries(m.values).filter(([k]) => !k.startsWith("_prior:"))
                      .map(([k, v]) => ` ${k}=${v ?? "—"}`).join("")}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
      <>
      <div className="space-y-3">
        <div>
          <label className="block text-sm text-neutral-400 mb-1" htmlFor="tr-name">Name</label>
          <input
            id="tr-name"
            className="bg-neutral-800 px-3 py-2 rounded w-full"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div className="flex gap-4">
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Profile</label>
            <select
              className="bg-neutral-800 px-3 py-2 rounded"
              value={profileId ?? ""}
              onChange={(e) => setProfileId(Number(e.target.value))}
            >
              {profilesQ.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1">Cooldown (sec)</label>
            <input
              type="number"
              className="bg-neutral-800 px-3 py-2 rounded w-24"
              value={form.cooldown_seconds}
              onChange={(e) => setForm({ ...form, cooldown_seconds: Number(e.target.value) })}
            />
          </div>
          <label className="flex items-center gap-2 mt-7">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            Enabled
          </label>
        </div>
      </div>

      <RuleBuilder
        value={form.condition}
        onChange={(c: Condition) => setForm({ ...form, condition: c })}
      />

      <div className="border-t border-neutral-800 pt-4 text-sm">
        <div className="text-neutral-400 mb-1">Preview — would currently fire?</div>
        {previewQ.isLoading && <div>Evaluating…</div>}
        {previewQ.isError && <div className="text-rose-400">Invalid condition</div>}
        {previewQ.data && (
          <div>
            <span className={previewQ.data.matched ? "text-emerald-400" : "text-neutral-400"}>
              {previewQ.data.matched ? "YES" : "NO"}
            </span>
            <span className="ml-2 text-neutral-500">
              {Object.entries(previewQ.data.values)
                .filter(([k]) => !k.startsWith("_prior:"))
                .map(([k, v]) => `${k}=${v ?? "—"}`)
                .join(", ")}
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
          onClick={() => save.mutate()}
          disabled={save.isPending || !form.name || !profileId}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          className="bg-neutral-800 px-4 py-2 rounded"
          onClick={() => navigate("/triggers")}
        >
          Cancel
        </button>
      </div>
      </>
      )}
    </div>
  );
}
