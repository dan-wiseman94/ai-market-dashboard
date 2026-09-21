import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/client";
import {
  isConsensusReport, isPostMortemReport,
  type ConsensusReport, type ObservationReport,
  type StructuredKind, type StructuredReport,
} from "@/api/observation";
import AiAttribution from "@/components/ai/AiAttribution";
import ConsensusReportCard from "@/components/ConsensusReportCard";
import ObservationReportCard from "@/components/ObservationReportCard";
import PostMortemReportBody from "@/components/PostMortemReportBody";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useProfiles } from "@/hooks/useProfiles";
import type { TradingProfile } from "@/api/profiles";

interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: {
    text?: string;
    kind?: StructuredKind;
    report?: StructuredReport;
    provider?: string;
    model?: string;
  };
  status?: "done" | "streaming" | "failed";
  error?: string;
  // One-shot structured runs record no Message, so this is null for their cards.
  ai_run?: { provider: string; model: string; cost_usd: string } | null;
  created_at: string;
}

interface ObserverThread {
  id: number;
  kind: string;
  profile_id: number;
  title: string;
  messages: Message[];
}

function isStructuredObservation(
  m: Message,
): m is Message & { content: { report: ObservationReport } } {
  return (
    m.role === "assistant" &&
    m.content.kind === "structured_observation" &&
    !!m.content.report &&
    !isConsensusReport(m.content.report)
  );
}

function isConsensus(m: Message): m is Message & { content: { report: ConsensusReport } } {
  return m.content.kind === "consensus_report" && isConsensusReport(m.content.report);
}

/** Every system row is a notice the fire wrote about itself — a cost-cap skip, a
 * missing key, an undecryptable one — not an answer from a model. */
function isNotice(m: Message): boolean {
  return m.role === "system";
}

function messageHeadline(m: Message): string {
  const when = new Date(m.created_at).toLocaleString();
  if (m.role === "user") return `📷 Snapshot — ${when}`;
  if (m.status === "failed") return `⚠️ Failed — ${when}`;
  // A reused observation cost nothing and is not a fresh read of the market.
  if (m.content.kind === "cached_observation") return `♻️ Cached observation — ${when}`;
  if (isConsensus(m)) {
    const r = m.content.report;
    return `🧭 Consensus — ${r.modal_bias ?? "no consensus"} · ${r.n_providers} providers — ${when}`;
  }
  if (isStructuredObservation(m)) return `📊 ${m.content.report.headline} — ${when}`;
  return `🤖 Response — ${when}`;
}

function MessageBody({ message }: { message: Message }) {
  if (message.status === "failed") {
    return (
      <div className="font-mono text-[13px] text-loss">
        {message.error || message.content.text || "unknown error"}
      </div>
    );
  }
  if (isConsensus(message)) return <ConsensusReportCard report={message.content.report} />;
  if (isStructuredObservation(message)) {
    return <ObservationReportCard report={message.content.report} />;
  }
  if (message.content.kind === "postmortem_report" && isPostMortemReport(message.content.report)) {
    return <PostMortemReportBody report={message.content.report} />;
  }
  return <div className="whitespace-pre-wrap">{message.content.text ?? ""}</div>;
}

function TimelineRow({
  message,
  isOpen,
  onToggle,
}: {
  message: Message;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const notice = isNotice(message);
  const run = message.ai_run;
  const provider = run?.provider ?? message.content.provider;
  const model = run?.model ?? message.content.model;

  return (
    <li
      className={`rounded border border-rule ${
        notice ? "bg-ink-850/50 text-ink-500" : "bg-ink-900"
      }`}
    >
      <div className="flex items-center gap-2 pr-3">
        <button type="button" onClick={onToggle} className="flex-1 px-3 py-2 text-left text-sm">
          {notice ? `🔒 ${message.content.text}` : messageHeadline(message)}
        </button>
        {!notice && message.status === "failed" && (
          <span className="ledger-pill" data-tone="loss">failed</span>
        )}
        {!notice && (
          <AiAttribution provider={provider} model={model} cost={run?.cost_usd} />
        )}
      </div>
      {isOpen && !notice && (
        <div className="px-3 pb-3 text-sm">
          <MessageBody message={message} />
        </div>
      )}
    </li>
  );
}

/**
 * Every profile has its own observer thread, so the timeline needs a way to
 * move between them — without this the only reachable timeline is whichever
 * profile something happened to link to.
 */
function ProfileSwitcher({
  profiles, profileId, onChange,
}: {
  profiles: TradingProfile[] | undefined;
  profileId: string | undefined;
  onChange: (id: number) => void;
}) {
  const rows = profiles ?? [];
  if (rows.length === 0) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-ink-500" htmlFor="observer-profile">
      Profile
      <select
        id="observer-profile"
        value={profileId ?? ""}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        className="px-2 py-1 rounded bg-ink-850 border border-rule text-ink-100"
      >
        {rows.map((p) => (
          <option key={p.id} value={String(p.id)}>{p.name}</option>
        ))}
      </select>
    </label>
  );
}

export default function ObserverTimelinePage() {
  const { profileId } = useParams<{ profileId: string }>();
  const navigate = useNavigate();
  const { data: profiles } = useProfiles();
  const { data: thread, isLoading } = useQuery({
    queryKey: ["observer-thread", profileId],
    queryFn: () => apiGet<ObserverThread>(`/api/observer/threads/${profileId}/`),
    enabled: !!profileId,
  });

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const toggle = (id: number) => setExpanded((e) => ({ ...e, [id]: !(e[id] ?? false) }));

  if (isLoading) {
    return (
      <main className="mx-auto max-w-3xl space-y-3 p-6">
        <SkeletonRows rows={4} />
      </main>
    );
  }
  const switcher = (
    <ProfileSwitcher
      profiles={profiles}
      profileId={profileId}
      onChange={(id) => navigate(`/threads/observer/${id}`)}
    />
  );

  if (!thread) {
    return (
      <main className="mx-auto max-w-3xl space-y-3 p-6">
        {switcher}
        <EmptyState title="No thread" body="The observer thread hasn't been created yet." />
      </main>
    );
  }

  const sorted = [...(thread.messages ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <main className="mx-auto max-w-3xl space-y-3 p-6 ledger-fade-in">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{thread.title}</h1>
        {switcher}
      </div>

      {sorted.length === 0 && (
        <EmptyState
          title="No observer activity yet"
          body="Fires will land here once the schedule runs."
        />
      )}

      <ul className="space-y-2">
        {sorted.map((m) => (
          <TimelineRow
            key={m.id}
            message={m}
            isOpen={expanded[m.id] ?? false}
            onToggle={() => toggle(m.id)}
          />
        ))}
      </ul>
    </main>
  );
}
