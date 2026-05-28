import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/client";
import ObservationReportCard, { type ObservationReport } from "@/components/ObservationReportCard";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: {
    text?: string;
    kind?: "structured_observation";
    report?: ObservationReport;
  };
  created_at: string;
}

interface ObserverThread {
  id: number;
  kind: string;
  profile_id: number;
  title: string;
  messages: Message[];
}

function isStructuredObservation(m: Message): m is Message & { content: { report: ObservationReport } } {
  return m.role === "assistant" && m.content.kind === "structured_observation" && !!m.content.report;
}

function isSkipped(m: Message): boolean {
  return m.role === "system" && (m.content.text ?? "").startsWith("⏸");
}

function messageHeadline(m: Message): string {
  const when = new Date(m.created_at).toLocaleString();
  if (m.role === "user") return `📷 Snapshot — ${when}`;
  if (isStructuredObservation(m)) return `📊 ${m.content.report.headline} — ${when}`;
  return `🤖 Response — ${when}`;
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
  const skipped = isSkipped(message);
  return (
    <li
      className={`rounded border ${skipped ? "border-slate-700 bg-slate-950/50 text-slate-500"
        : "border-slate-700 bg-slate-900"}`}
    >
      <button type="button" onClick={onToggle} className="w-full text-left px-3 py-2 text-sm">
        {skipped ? `🔒 ${message.content.text}` : messageHeadline(message)}
      </button>
      {isOpen && !skipped && (
        <div className="px-3 pb-3 text-sm">
          {isStructuredObservation(message)
            ? <ObservationReportCard report={message.content.report} />
            : <div className="whitespace-pre-wrap">{message.content.text ?? ""}</div>}
        </div>
      )}
    </li>
  );
}

export default function ObserverTimelinePage() {
  const { profileId } = useParams<{ profileId: string }>();
  const { data: thread, isLoading } = useQuery({
    queryKey: ["observer-thread", profileId],
    queryFn: () => apiGet<ObserverThread>(`/api/observer/threads/${profileId}/`),
    enabled: !!profileId,
  });

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const toggle = (id: number) =>
    setExpanded((e) => ({ ...e, [id]: !(e[id] ?? false) }));

  if (isLoading) {
    return (
      <main className="p-6 max-w-3xl mx-auto space-y-3">
        <SkeletonRows rows={4} />
      </main>
    );
  }
  if (!thread) {
    return (
      <main className="p-6 max-w-3xl mx-auto">
        <EmptyState title="No thread" body="The observer thread hasn't been created yet." />
      </main>
    );
  }

  const sorted = [...(thread.messages ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-3">
      <h1 className="text-2xl font-semibold">{thread.title}</h1>

      {sorted.length === 0 && (
        <EmptyState title="No observer activity yet" body="Fires will land here once the schedule runs." />
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
