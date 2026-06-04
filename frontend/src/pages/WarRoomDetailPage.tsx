import { useParams } from "react-router-dom";

import type { WarRoomMessage, WarRoomVerdict } from "@/api/warroom";
import { Skeleton } from "@/components/Skeleton";
import { useWarRoomLive, type WarRoomLiveMessage } from "@/hooks/useWarRoomLive";
import { useWarRoomRun } from "@/hooks/useWarroom";

const PERSONA_LABEL: Record<string, string> = { bull: "Bull", bear: "Bear", skeptic: "Skeptic" };

const PERSONAS = ["bull", "bear", "skeptic"] as const;

function groupByPersona(messages: WarRoomMessage[]): Record<string, string[]> {
  const personaMsgs = messages.filter((m) => (m.content as Record<string, unknown>)?.persona);
  const byPersona: Record<string, string[]> = { bull: [], bear: [], skeptic: [] };
  for (const m of personaMsgs) {
    const c = m.content as Record<string, unknown>;
    const p = String(c.persona);
    if (byPersona[p]) byPersona[p].push(String(c.text ?? ""));
  }
  return byPersona;
}

function LiveDebate({ streaming, messages }: { streaming: boolean; messages: WarRoomLiveMessage[] }) {
  return (
    <div className="mt-6 rounded border border-rule p-3" data-testid="warroom-live">
      <div className="text-xs uppercase tracking-wide text-ink/60">
        Live debate {streaming ? "· streaming…" : "· thinking…"}
      </div>
      {messages.length === 0 ? (
        <div className="mt-1 text-sm text-ink/40">Waiting for the first argument…</div>
      ) : (
        messages.map((m) => (
          <p key={m.id} className="mt-2 whitespace-pre-wrap text-sm text-ink/80">
            {m.text}
            {m.status === "streaming" && <span className="text-copper">▍</span>}
          </p>
        ))
      )}
    </div>
  );
}

function PersonaLanes({ byPersona }: { byPersona: Record<string, string[]> }) {
  return (
    <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
      {PERSONAS.map((p) => (
        <div key={p} className="rounded border border-rule p-3">
          <div className="text-xs uppercase tracking-wide text-ink/60">{PERSONA_LABEL[p]}</div>
          {byPersona[p].length === 0 ? (
            <div className="mt-1 text-sm text-ink/40">—</div>
          ) : (
            byPersona[p].map((t, i) => <p key={i} className="mt-2 text-sm text-ink/80">{t}</p>)
          )}
        </div>
      ))}
    </div>
  );
}

function Verdict({ v }: { v: WarRoomVerdict }) {
  return (
    <div className="mt-6 rounded border border-copper/40 bg-copper/5 p-4">
      <div className="text-xs uppercase tracking-wide text-ink/60">Verdict</div>
      <div className="mt-1 text-lg font-semibold">{v.verdict}{v.confidence != null && <span className="text-ink/50"> ({(v.confidence * 100).toFixed(0)}% conf)</span>}</div>
      {v.strongest_bull && <p className="mt-2 text-sm"><b>Strongest bull:</b> {v.strongest_bull}</p>}
      {v.strongest_bear && <p className="mt-1 text-sm"><b>Strongest bear:</b> {v.strongest_bear}</p>}
      {v.what_would_change_my_mind && <p className="mt-1 text-sm"><b>What would change my mind:</b> {v.what_would_change_my_mind}</p>}
    </div>
  );
}

export default function WarRoomDetailPage() {
  const { id } = useParams();
  const { data: run, isLoading } = useWarRoomRun(Number(id));
  const isRunning = run?.status === "running";
  const live = useWarRoomLive(run?.thread_id ?? null, isRunning);
  if (isLoading || !run) return <Skeleton where="warroom-detail" />;

  const byPersona = groupByPersona(run.messages);
  const v = run.verdict;

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">War Room — {run.subject_label}</h1>
      <div className="mt-1 text-sm text-ink/60">{run.status}{run.status === "error" && run.error ? `: ${run.error}` : ""}</div>

      {isRunning && <LiveDebate streaming={live.streaming} messages={live.messages} />}

      <PersonaLanes byPersona={byPersona} />

      {v?.verdict && <Verdict v={v} />}
    </div>
  );
}
