import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTrigger, evaluateTrigger, fetchTriggers, updateTrigger,
  backtestTrigger, type BacktestMatch,
} from "@/api/triggers";
import FiringsTable from "@/components/triggers/FiringsTable";
import { useProfiles } from "@/hooks/useProfiles";
import BacktestPanel from "./trigger-editor/BacktestPanel";
import ConditionForm, { type TriggerForm } from "./trigger-editor/ConditionForm";

const EMPTY: TriggerForm = {
  name: "",
  condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] },
  cooldown_seconds: 1800,
  enabled: true,
};

type Tab = "condition" | "firings" | "backtest";

function TabButton({
  active, label, onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`py-2 ${active ? "text-ink-900 border-b-2 border-indigo-500 dark:text-white" : "text-neutral-400"}`}
      onClick={onClick}
    >{label}</button>
  );
}

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

  const profilesQ = useProfiles();

  const triggersQ = useQuery({
    queryKey: ["triggers"],
    queryFn: fetchTriggers,
    enabled: !isNew,
  });

  const existing = triggersQ.data?.find((t) => t.id === id);
  const [form, setForm] = useState(EMPTY);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("condition");
  // Lazy initializers keep these impure Date reads out of render
  // (react-hooks/purity: "Cannot call impure function during render").
  const [btStart, setBtStart] = useState(() =>
    new Date(Date.now() - 90 * 24 * 3600_000).toISOString().slice(0, 10),
  );
  const [btEnd, setBtEnd] = useState(() => new Date().toISOString().slice(0, 10));
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

  // Seed the form from the loaded trigger, and default the profile to the first
  // one once profiles load. Render-phase guarded updates instead of effects
  // (avoids react-hooks/set-state-in-effect), keyed to match the prior
  // [existing] / [profilesQ.data, profileId] dependencies.
  const [seededExisting, setSeededExisting] = useState(existing);
  if (existing && existing !== seededExisting) {
    setSeededExisting(existing);
    setForm({
      name: existing.name,
      condition: existing.condition,
      cooldown_seconds: existing.cooldown_seconds,
      enabled: existing.enabled,
    });
    setProfileId(existing.profile);
  }
  if (profilesQ.data && profileId === null && profilesQ.data.length > 0) {
    setProfileId(profilesQ.data[0].id);
  }

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

  function renderBody() {
    if (!isNew && tab === "firings") {
      return <FiringsTable triggerId={id!} />;
    }
    if (tab === "backtest") {
      return (
        <BacktestPanel
          start={btStart}
          onStartChange={setBtStart}
          end={btEnd}
          onEndChange={setBtEnd}
          backtest={backtest}
          result={btResult}
        />
      );
    }
    return (
      <ConditionForm
        form={form}
        onFormChange={setForm}
        profiles={profilesQ.data}
        profileId={profileId}
        onProfileChange={setProfileId}
        preview={previewQ}
        save={save}
        onCancel={() => navigate("/triggers")}
      />
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold">
        {isNew ? "New trigger" : `Edit trigger: ${existing?.name ?? ""}`}
      </h1>

      {!isNew && (
        <div className="flex gap-4 border-b border-neutral-800 mb-4">
          <TabButton active={tab === "condition"} label="Condition" onClick={() => setTab("condition")} />
          <TabButton active={tab === "firings"} label={`Firings (${existing?.firings_count ?? 0})`} onClick={() => setTab("firings")} />
          <TabButton active={tab === "backtest"} label="Backtest" onClick={() => setTab("backtest")} />
        </div>
      )}

      {renderBody()}
    </div>
  );
}
