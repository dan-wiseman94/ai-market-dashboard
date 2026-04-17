import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import StreamingMessage from "@/components/StreamingMessage";
import { useChannel } from "@/hooks/useChannel";
import { useSendMessage, useThread } from "@/hooks/useThread";
import { useSnapshot } from "@/hooks/useSnapshot";

type LiveMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  status: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
};

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const tid = id ? parseInt(id, 10) : null;
  const snapshotId = search.get("snapshot") ? parseInt(search.get("snapshot")!, 10) : null;

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  useEffect(() => {
    if (!thread) return;
    const seed: Record<number, LiveMessage> = {};
    for (const m of thread.messages) {
      seed[m.id] = {
        id: m.id,
        role: m.role === "system" ? "assistant" : m.role,
        text: m.content?.text ?? "",
        status: m.status,
        error: m.error,
        cost: m.ai_run?.cost_usd,
        model: m.ai_run?.model,
      };
    }
    setLive(seed);
  }, [thread]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onWs = useCallback((msg: any) => {
    if (msg.event === "message_started") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { id: msg.message_id, role: "assistant", text: "", status: "streaming" },
      }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? { id: msg.message_id, role: "assistant", text: "", status: "streaming" as const };
        return { ...prev, [msg.message_id]: { ...cur, text: cur.text + msg.text } };
      });
    } else if (msg.event === "message_done") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "done", cost: msg.cost_usd },
      }));
      refetch();
    } else if (msg.event === "error" || msg.event === "cost_capped") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "failed", error: msg.error },
      }));
    }
  }, [refetch]);

  useChannel(tid ? `thread.${tid}` : null, onWs);

  const send = useSendMessage(tid ?? 0);
  const [input, setInput] = useState("");

  const ordered = useMemo(
    () => Object.values(live).sort((a, b) => a.id - b.id),
    [live],
  );

  if (!thread) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">{thread.title || `Thread #${thread.id}`}</h1>
        <Link to="/" className="text-sm text-slate-300 hover:underline">← Dashboard</Link>
      </div>

      {snap && (
        <details className="p-3 rounded border border-slate-800">
          <summary className="cursor-pointer text-sm text-slate-300">
            Snapshot #{snap.id} · {snap.status} · {snap.includes.join(", ")}
          </summary>
          <pre className="mt-2 text-xs text-slate-400 overflow-x-auto">
            {JSON.stringify(
              snap.sections.map((s) => ({ kind: s.kind, status: s.status, error: s.error })),
              null, 2,
            )}
          </pre>
        </details>
      )}

      <section className="space-y-3">
        {ordered.map((m) => (
          <StreamingMessage key={m.id}
            role={m.role} text={m.text} status={m.status}
            error={m.error} cost={m.cost} model={m.model}
          />
        ))}
      </section>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim()) return;
          send.mutate(input.trim(), { onSuccess: () => setInput("") });
        }}
      >
        <input
          value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={thread.kind === "consult" ? "Follow-up…" : "Message"}
          className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Send</button>
      </form>
    </main>
  );
}
