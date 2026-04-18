import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import BranchTabs from "@/components/BranchTabs";
import CompareTotalsStrip from "@/components/CompareTotalsStrip";
import CompareDialog from "@/components/CompareDialog";
import ProviderModelPicker from "@/components/ProviderModelPicker";
import StopButton from "@/components/StopButton";
import StreamingMessage from "@/components/StreamingMessage";
import { useChannel } from "@/hooks/useChannel";
import { useBranchState, type BranchEvent } from "@/hooks/useBranchState";
import { useSnapshot } from "@/hooks/useSnapshot";
import { useCompareMessage, useSendMessage, useStopMessage, useThread } from "@/hooks/useThread";

type LiveMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  status: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
  provider?: string;
  parent_message_id?: number | null;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type WsMsg = any;

function BranchGroup({
  parentMsg,
  branches,
  activeId,
  onSelect,
  threadChannel,
}: {
  parentMsg: { id: number };
  branches: LiveMessage[];
  activeId: number | null;
  onSelect: (id: number) => void;
  threadChannel: string | null;
}) {
  const { state, handleEvent } = useBranchState(parentMsg.id);

  const onWsBranch = useCallback((msg: WsMsg) => {
    handleEvent(msg as BranchEvent);
  }, [handleEvent]);

  useChannel(threadChannel, onWsBranch);

  const branchTabs = branches.map((m) => ({
    id: m.id,
    label: `${state[m.id]?.provider ?? m.provider ?? "?"} / ${state[m.id]?.model ?? m.model ?? "?"}`,
    status: (state[m.id]?.status ?? (m.status === "streaming" ? "streaming" : m.status === "failed" ? "failed" : "done")) as "streaming" | "done" | "failed",
    cost: state[m.id]?.cost ?? (m.cost != null ? Number(m.cost) : undefined),
  }));

  return (
    <>
      {branchTabs.length > 0 && (
        <BranchTabs branches={branchTabs} activeId={activeId} onSelect={onSelect} />
      )}
      {branchTabs.length > 1 && <CompareTotalsStrip state={state} />}
    </>
  );
}

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const tid = id ? parseInt(id, 10) : null;
  const snapshotId = search.get("snapshot") ? parseInt(search.get("snapshot")!, 10) : null;

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  const [activeBranchByParent, setActiveBranchByParent] = useState<Record<number, number>>({});
  const [picker, setPicker] = useState({ provider: "claude", model: "claude-sonnet-4-6" });
  const [showCompare, setShowCompare] = useState(false);

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
        provider: m.ai_run?.provider,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        parent_message_id: (m as any).parent_message_id ?? null,
      };
    }
    setLive(seed);
  }, [thread]);

  const onWs = useCallback((msg: WsMsg) => {
    if (msg.event === "message_started") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: {
          id: msg.message_id, role: "assistant", text: "", status: "streaming",
          model: msg.model, provider: msg.provider,
          parent_message_id: msg.parent_message_id ?? null,
        },
      }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? {
          id: msg.message_id, role: "assistant" as const, text: "", status: "streaming" as const,
        };
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
  const compare = useCompareMessage(tid ?? 0);
  const stop = useStopMessage(tid ?? 0);
  const [input, setInput] = useState("");

  const { ordered, branchesByParent } = useMemo(() => {
    const arr = Object.values(live).sort((a, b) => a.id - b.id);
    const byParent: Record<number, LiveMessage[]> = {};
    const top: LiveMessage[] = [];
    for (const m of arr) {
      if (m.role === "assistant" && m.parent_message_id != null) {
        (byParent[m.parent_message_id] ??= []).push(m);
      } else {
        top.push(m);
      }
    }
    return { ordered: top, branchesByParent: byParent };
  }, [live]);

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
            {JSON.stringify(snap.sections.map((s) => ({ kind: s.kind, status: s.status, error: s.error })), null, 2)}
          </pre>
        </details>
      )}

      <section className="space-y-3">
        {ordered.map((m) => {
          if (m.role === "user") {
            const children = branchesByParent[m.id] ?? [];
            const activeId = activeBranchByParent[m.id] ?? children[0]?.id ?? null;
            const active = children.find((c) => c.id === activeId) ?? children[0];
            return (
              <div key={m.id} className="space-y-2">
                <StreamingMessage role="user" text={m.text} status={m.status} />
                {children.length > 0 && (
                  <>
                    <BranchGroup
                      parentMsg={m}
                      branches={children}
                      activeId={activeId}
                      onSelect={(cid) => setActiveBranchByParent((s) => ({ ...s, [m.id]: cid }))}
                      threadChannel={tid ? `thread.${tid}` : null}
                    />
                    {active && (
                      <div className="flex items-start gap-2">
                        <div className="flex-1">
                          <StreamingMessage
                            role={active.role} text={active.text} status={active.status}
                            error={active.error} cost={active.cost} model={active.model}
                          />
                        </div>
                        {active.status === "streaming" && (
                          <StopButton onStop={() => stop.mutate(active.id)} />
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          }
          return (
            <div key={m.id} className="flex items-start gap-2">
              <div className="flex-1">
                <StreamingMessage
                  role={m.role} text={m.text} status={m.status}
                  error={m.error} cost={m.cost} model={m.model}
                />
              </div>
              {m.status === "streaming" && <StopButton onStop={() => stop.mutate(m.id)} />}
            </div>
          );
        })}
      </section>

      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Reply with:</span>
          <ProviderModelPicker value={picker} onChange={setPicker} />
          <button
            className="ml-auto px-2 py-1 rounded bg-slate-800 hover:bg-slate-700"
            onClick={() => setShowCompare(true)}
          >
            Compare…
          </button>
        </div>
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
            placeholder="Message"
            className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
          <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Send</button>
        </form>
      </div>

      {showCompare && (
        <CompareDialog
          onCancel={() => setShowCompare(false)}
          onSubmit={(text, branches) => {
            compare.mutate({ text, branches });
            setShowCompare(false);
          }}
        />
      )}
    </main>
  );
}
