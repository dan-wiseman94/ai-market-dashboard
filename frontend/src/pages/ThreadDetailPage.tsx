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
import ThreadExportButton from "@/components/ThreadExportButton";

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

  if (!thread) {
    return (
      <main className="px-8 py-8 max-w-4xl mx-auto">
        <div className="font-mono text-[13px] text-ink-400">Loading thread…</div>
      </main>
    );
  }

  return (
    <main className="px-8 py-8 max-w-4xl mx-auto ledger-fade-in">
      {/* Masthead */}
      <header className="mb-8 pb-6 border-b border-rule">
        <div className="flex items-center gap-3 mb-3">
          <span className="ledger-eyebrow">Thread · #{thread.id}</span>
          <span className="flex-1 h-px bg-rule-soft" />
          <ThreadExportButton threadId={tid!} />
          <Link
            to="/"
            className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors uppercase tracking-wider"
          >
            ← Desk
          </Link>
        </div>
        <h1
          className="ledger-display"
          style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}
        >
          {thread.title || <em className="italic text-copper-300">Untitled consultation</em>}
        </h1>
      </header>

      {/* Snapshot context — folded */}
      {snap && (
        <details className="group mb-8 ledger-surface">
          <summary className="cursor-pointer list-none px-5 py-3 flex items-center gap-3 hover:bg-copper-500/[0.04] transition-colors">
            <span aria-hidden className="font-mono text-[10px] text-copper-400 group-open:rotate-90 transition-transform duration-200">▸</span>
            <span className="ledger-eyebrow">Context</span>
            <span className="font-mono text-[12px] text-ink-200">Snapshot #{snap.id}</span>
            <span className="font-mono text-[11px] text-ink-500">· {snap.status} · {snap.includes.join(", ")}</span>
          </summary>
          <div className="px-5 py-3 border-t border-rule-soft">
            <pre className="font-mono text-[11px] text-ink-400 overflow-x-auto leading-relaxed">
              {JSON.stringify(snap.sections.map((s: { kind: string; status: string; error?: string }) => ({ kind: s.kind, status: s.status, error: s.error })), null, 2)}
            </pre>
          </div>
        </details>
      )}

      {/* Conversation */}
      <section className="space-y-6">
        {ordered.map((m) => {
          if (m.role === "user") {
            const children = branchesByParent[m.id] ?? [];
            const activeId = activeBranchByParent[m.id] ?? children[0]?.id ?? null;
            const active = children.find((c) => c.id === activeId) ?? children[0];
            return (
              <div key={m.id} className="space-y-4">
                <StreamingMessage role="user" text={m.text} status={m.status} />
                {children.length > 0 && (
                  <div className="ledger-surface overflow-hidden">
                    <BranchGroup
                      parentMsg={m}
                      branches={children}
                      activeId={activeId}
                      onSelect={(cid) => setActiveBranchByParent((s) => ({ ...s, [m.id]: cid }))}
                      threadChannel={tid ? `thread.${tid}` : null}
                    />
                    {active && (
                      <div className="flex items-start gap-2 p-0">
                        <div className="flex-1 min-w-0 px-6 py-5">
                          <StreamingMessage
                            bare
                            role={active.role} text={active.text} status={active.status}
                            error={active.error} cost={active.cost} model={active.model} provider={active.provider}
                          />
                        </div>
                        {active.status === "streaming" && (
                          <div className="pt-5 pr-4">
                            <StopButton onStop={() => stop.mutate(active.id)} />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          }
          return (
            <div key={m.id} className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <StreamingMessage
                  role={m.role} text={m.text} status={m.status}
                  error={m.error} cost={m.cost} model={m.model} provider={m.provider}
                />
              </div>
              {m.status === "streaming" && (
                <div className="pt-5">
                  <StopButton onStop={() => stop.mutate(m.id)} />
                </div>
              )}
            </div>
          );
        })}
      </section>

      {/* Compose bar */}
      <div
        className="mt-10 ledger-surface overflow-hidden"
        style={{ boxShadow: "0 -2px 40px -20px rgba(200,150,88,0.25)" }}
      >
        <div className="flex items-center gap-3 px-5 py-2.5 border-b border-rule-soft bg-ink-void/30">
          <span className="ledger-eyebrow">Reply with</span>
          <div className="flex-1">
            <ProviderModelPicker value={picker} onChange={setPicker} />
          </div>
          <button
            className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
            onClick={() => setShowCompare(true)}
          >
            ⇌ Compare
          </button>
        </div>
        <form
          className="flex items-stretch"
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim()) return;
            send.mutate(input.trim(), { onSuccess: () => setInput("") });
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Continue the thread…"
            className="flex-1 px-5 py-4 bg-transparent border-0 focus:outline-none font-display text-[15px] text-ink-100 placeholder:text-ink-500"
            style={{ fontVariationSettings: '"opsz" 18' }}
          />
          <button className="ledger-cta rounded-none border-y-0 border-r-0 px-6">
            Send
            <span aria-hidden className="font-mono text-[11px] opacity-70">⏎</span>
          </button>
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

