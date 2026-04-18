import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/client";

interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: { text?: string };
  created_at: string;
}

interface ObserverThread {
  id: number;
  kind: string;
  profile_id: number;
  title: string;
  messages: Message[];
}

export default function ObserverTimelinePage() {
  const { profileId } = useParams<{ profileId: string }>();
  const { data: thread, isLoading } = useQuery({
    queryKey: ["observer-thread", profileId],
    queryFn: () => apiGet<ObserverThread>(`/api/observer/threads/${profileId}/`),
    enabled: !!profileId,
  });

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  if (isLoading) return <main className="p-6">Loading…</main>;
  if (!thread) return <main className="p-6">No thread.</main>;

  const sorted = [...(thread.messages ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-3">
      <h1 className="text-2xl font-semibold">{thread.title}</h1>

      {sorted.length === 0 && <p className="text-slate-500">No observer activity yet.</p>}

      <ul className="space-y-2">
        {sorted.map((m) => {
          const isOpen = expanded[m.id] ?? false;
          const headline = m.role === "user"
            ? `📷 Snapshot — ${new Date(m.created_at).toLocaleString()}`
            : `🤖 Response — ${new Date(m.created_at).toLocaleString()}`;
          const isSkipped = m.role === "system" && (m.content.text ?? "").startsWith("⏸");
          return (
            <li key={m.id}
                className={`rounded border ${isSkipped ? "border-slate-700 bg-slate-950/50 text-slate-500"
                  : "border-slate-700 bg-slate-900"}`}>
              <button type="button" onClick={() => setExpanded((e) => ({ ...e, [m.id]: !isOpen }))}
                      className="w-full text-left px-3 py-2 text-sm">
                {isSkipped ? `🔒 ${m.content.text}` : headline}
              </button>
              {isOpen && !isSkipped && (
                <div className="px-3 pb-3 text-sm whitespace-pre-wrap">{m.content.text ?? ""}</div>
              )}
            </li>
          );
        })}
      </ul>
    </main>
  );
}
