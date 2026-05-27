import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
import { ToolCallTrace, type ToolCallRecord } from "@/components/ToolCallTrace";
import { FileAttachPanel } from "@/components/FileAttachPanel";
import { useFiles, useAttachFileToThread } from "@/hooks/useFiles";
import { useCreateThesis } from "@/hooks/useTheses";
import { useToast } from "@/hooks/useToast";
import type { ThesisDirection } from "@/api/thesis";
import { useJournal, useCreateJournalEntry } from "@/hooks/useJournal";
import type { JournalDecision } from "@/api/journal";
import { EmptyState } from "@/components/EmptyState";

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
  const navigate = useNavigate();

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  // New thesis from this thread
  const createThesis = useCreateThesis();
  const { push } = useToast();
  const [showThesisForm, setShowThesisForm] = useState(false);
  const [thesisTitle, setThesisTitle] = useState("");
  const [thesisTicker, setThesisTicker] = useState("");
  const [thesisDirection, setThesisDirection] = useState<ThesisDirection>("bullish");
  const [thesisConviction, setThesisConviction] = useState(3);
  const [thesisTarget, setThesisTarget] = useState("");
  const [thesisInvalidation, setThesisInvalidation] = useState("");

  // Close & journal panel state
  const [showJournalPanel, setShowJournalPanel] = useState(false);
  const [journalDecision, setJournalDecision] = useState<JournalDecision>("acted");
  const [journalNote, setJournalNote] = useState("");
  // promoteMode: when true, submitting the thesis form also logs a linked journal entry
  const [promoteMode, setPromoteMode] = useState(false);

  const createJournalEntry = useCreateJournalEntry();
  const { data: journalEntries = [] } = useJournal(tid);

  const handleCreateThesis = (e: React.FormEvent) => {
    e.preventDefault();
    createThesis.mutate(
      {
        title: thesisTitle,
        ticker: thesisTicker,
        direction: thesisDirection,
        conviction: thesisConviction,
        target_price: thesisTarget || null,
        invalidation_price: thesisInvalidation || null,
        thread_id: tid,
        snapshot_id: thread?.pinned_snapshot_id ?? undefined,
        profile_id: thread?.profile?.id ?? undefined,
      },
      {
        onSuccess: (thesis) => {
          push({ kind: "success", text: `Thesis created: ${thesis.title}` });
          // In promote mode, link a journal entry to the newly created thesis
          if (promoteMode && tid) {
            createJournalEntry.mutate(
              {
                thread_id: tid,
                decision: journalDecision,
                note: journalNote.trim() || "Promoted to thesis",
                thesis_id: thesis.id,
                snapshot_id: thread?.pinned_snapshot_id ?? undefined,
              },
              {
                onError: () =>
                  push({ kind: "error", text: "Thesis created, but journaling the decision failed." }),
              },
            );
          }
          setShowThesisForm(false);
          setPromoteMode(false);
          setThesisTitle("");
          setThesisTicker("");
          setThesisDirection("bullish");
          setThesisConviction(3);
          setThesisTarget("");
          setThesisInvalidation("");
          navigate(`/theses/${thesis.id}`);
        },
        onError: (err) =>
          push({ kind: "error", text: (err as Error).message }),
      },
    );
  };

  const handleLogDecision = () => {
    if (!tid) return;
    createJournalEntry.mutate(
      {
        thread_id: tid,
        decision: journalDecision,
        note: journalNote.trim() || undefined,
        snapshot_id: thread?.pinned_snapshot_id ?? undefined,
      },
      {
        onSuccess: () => {
          push({ kind: "success", text: "Decision logged." });
          setJournalDecision("acted");
          setJournalNote("");
          setShowJournalPanel(false);
        },
        onError: (err) =>
          push({ kind: "error", text: (err as Error).message }),
      },
    );
  };

  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  const [activeBranchByParent, setActiveBranchByParent] = useState<Record<number, number>>({});
  const [picker, setPicker] = useState({ provider: "claude", model: "claude-sonnet-4-6" });
  const [showCompare, setShowCompare] = useState(false);
  // Per-assistant-message map of tool_use_id → ToolCallRecord.
  const [toolCalls, setToolCalls] = useState<
    Record<number, Record<string, ToolCallRecord>>
  >({});

  // Seed the live-message map from the loaded thread. Render-phase guarded
  // update keyed on the thread object (matches the prior effect's [thread] dep)
  // instead of an effect, per react-hooks v7 (set-state-in-effect).
  const [prevThread, setPrevThread] = useState<typeof thread>(undefined);
  if (thread !== prevThread) {
    setPrevThread(thread);
    if (thread) {
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
    }
  }

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
    } else if (msg.event === "tool_call") {
      setToolCalls((prev) => {
        const bucket = { ...(prev[msg.message_id] ?? {}) };
        bucket[msg.tool_use_id] = {
          toolUseId: msg.tool_use_id,
          name: msg.name,
          input: msg.input,
          ok: true,
          latencyMs: 0,
        };
        return { ...prev, [msg.message_id]: bucket };
      });
    } else if (msg.event === "tool_result") {
      setToolCalls((prev) => {
        const bucket = { ...(prev[msg.message_id] ?? {}) };
        const existing = bucket[msg.tool_use_id];
        if (existing) {
          bucket[msg.tool_use_id] = {
            ...existing,
            ok: !!msg.ok,
            latencyMs: msg.latency_ms ?? 0,
          };
        }
        return { ...prev, [msg.message_id]: bucket };
      });
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
          <button
            onClick={() => setShowJournalPanel((v) => !v)}
            className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
            data-testid="journal-panel-btn"
          >
            ✎ Close & journal
          </button>
          <button
            onClick={() => setShowThesisForm((v) => !v)}
            className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
            data-testid="new-thesis-btn"
          >
            + New thesis from this
          </button>
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

      {/* New thesis inline form */}
      {showThesisForm && (
        <form
          onSubmit={handleCreateThesis}
          className="ledger-surface px-5 py-4 mb-8 space-y-4"
          data-testid="new-thesis-form"
        >
          <div className="ledger-eyebrow mb-1">{promoteMode ? "Promote to thesis" : "New thesis from this thread"}</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label htmlFor="thesis-title" className="block text-[12px] text-ink-400 mb-1">Title</label>
              <input
                id="thesis-title"
                required
                value={thesisTitle}
                onChange={(e) => setThesisTitle(e.target.value)}
                placeholder="e.g. SPY breaks 600 by Q3"
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500"
              />
            </div>
            <div>
              <label htmlFor="thesis-ticker" className="block text-[12px] text-ink-400 mb-1">Ticker</label>
              <input
                id="thesis-ticker"
                required
                value={thesisTicker}
                onChange={(e) => setThesisTicker(e.target.value.toUpperCase())}
                placeholder="SPY"
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500"
              />
            </div>
            <div>
              <label htmlFor="thesis-direction" className="block text-[12px] text-ink-400 mb-1">Direction</label>
              <select
                id="thesis-direction"
                value={thesisDirection}
                onChange={(e) => setThesisDirection(e.target.value as ThesisDirection)}
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
              >
                <option value="bullish">Bullish</option>
                <option value="bearish">Bearish</option>
                <option value="neutral">Neutral</option>
              </select>
            </div>
            <div>
              <label htmlFor="thesis-conviction" className="block text-[12px] text-ink-400 mb-1">Conviction (1–5)</label>
              <input
                id="thesis-conviction"
                type="number"
                min={1}
                max={5}
                value={thesisConviction}
                onChange={(e) => setThesisConviction(Number(e.target.value))}
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
              />
            </div>
            <div>
              <label htmlFor="thesis-target" className="block text-[12px] text-ink-400 mb-1">Target price (optional)</label>
              <input
                id="thesis-target"
                value={thesisTarget}
                onChange={(e) => setThesisTarget(e.target.value)}
                placeholder="600.00"
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500"
              />
            </div>
            <div>
              <label htmlFor="thesis-invalidation" className="block text-[12px] text-ink-400 mb-1">Invalidation price (optional)</label>
              <input
                id="thesis-invalidation"
                value={thesisInvalidation}
                onChange={(e) => setThesisInvalidation(e.target.value)}
                placeholder="540.00"
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500"
              />
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={createThesis.isPending}
              className="ledger-cta px-4 py-1.5 text-[13px]"
            >
              {createThesis.isPending ? "Creating…" : "Create thesis"}
            </button>
            <button
              type="button"
              className="ledger-ghost px-4 py-1.5 text-[13px]"
              onClick={() => {
                setShowThesisForm(false);
                setPromoteMode(false);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Close & journal panel */}
      {showJournalPanel && (
        <div
          className="ledger-surface px-5 py-4 mb-8 space-y-4"
          data-testid="journal-panel"
        >
          <div className="ledger-eyebrow mb-1">Close &amp; journal this thread</div>

          {/* Decision log form */}
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label htmlFor="journal-decision" className="block text-[12px] text-ink-400 mb-1">Decision</label>
              <select
                id="journal-decision"
                value={journalDecision}
                onChange={(e) => setJournalDecision(e.target.value as JournalDecision)}
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500"
                data-testid="journal-decision-select"
              >
                <option value="acted">Acted</option>
                <option value="passed">Passed</option>
                <option value="watching">Watching</option>
                <option value="hedged">Hedged</option>
              </select>
            </div>
            <div className="col-span-2">
              <label htmlFor="journal-note" className="block text-[12px] text-ink-400 mb-1">Note (optional)</label>
              <textarea
                id="journal-note"
                value={journalNote}
                onChange={(e) => setJournalNote(e.target.value)}
                placeholder="What did you decide and why?"
                rows={3}
                className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 w-full focus:outline-none focus:border-copper-500 placeholder:text-ink-500 resize-none"
                data-testid="journal-note-textarea"
              />
            </div>
          </div>
          <div className="flex gap-2 pt-1 flex-wrap">
            <button
              type="button"
              disabled={createJournalEntry.isPending}
              onClick={handleLogDecision}
              className="ledger-cta px-4 py-1.5 text-[13px]"
              data-testid="journal-log-btn"
            >
              {createJournalEntry.isPending ? "Logging…" : "Log decision"}
            </button>
            <button
              type="button"
              onClick={() => {
                setPromoteMode(true);
                setShowThesisForm(true);
              }}
              className="ledger-ghost px-4 py-1.5 text-[13px]"
              data-testid="journal-promote-btn"
            >
              Promote to thesis
            </button>
            <button
              type="button"
              className="ledger-ghost px-4 py-1.5 text-[13px] ml-auto"
              onClick={() => setShowJournalPanel(false)}
            >
              Close
            </button>
          </div>

          {/* Existing journal entries */}
          <div className="border-t border-rule-soft pt-4 mt-2">
            <div className="ledger-eyebrow mb-3">Prior decisions</div>
            {journalEntries.length === 0 ? (
              <EmptyState title="No decisions logged yet" body="Use the form above to record what you decided on this thread." />
            ) : (
              <ul className="space-y-3" data-testid="journal-entries-list">
                {journalEntries.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-3 py-2 border-b border-rule-soft last:border-b-0" data-testid={`journal-entry-${entry.id}`}>
                    <span className={`font-mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border shrink-0 mt-0.5 ${
                      entry.decision === "acted"
                        ? "text-emerald-700 border-emerald-500/40 bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-800 dark:bg-emerald-950/40"
                        : entry.decision === "passed"
                        ? "text-slate-400 border-slate-700 bg-slate-900/40"
                        : entry.decision === "watching"
                        ? "text-amber-700 border-amber-500/40 bg-amber-500/10 dark:text-amber-400 dark:border-amber-800 dark:bg-amber-950/40"
                        : "text-violet-700 border-violet-500/40 bg-violet-500/10 dark:text-violet-400 dark:border-violet-800 dark:bg-violet-950/40"
                    }`}>
                      {entry.decision}
                    </span>
                    <div className="flex-1 min-w-0">
                      {entry.note && (
                        <p className="text-[13px] text-ink-100 leading-relaxed mb-1">{entry.note}</p>
                      )}
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="font-mono text-[11px] text-ink-500">
                          {new Date(entry.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                        </span>
                        {entry.thesis_id != null && (
                          <Link
                            to={`/theses/${entry.thesis_id}`}
                            className="font-mono text-[11px] text-copper-300 hover:text-copper-200 transition-colors"
                            data-testid={`journal-thesis-link-${entry.id}`}
                          >
                            → Thesis #{entry.thesis_id}
                          </Link>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

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
              <div key={m.id} data-testid={`message-${m.id}`} className="space-y-4">
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
          const calls = Object.values(toolCalls[m.id] ?? {});
          return (
            <div key={m.id} data-testid={`message-${m.id}`} className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <ToolCallTrace calls={calls} />
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
            send.mutate(
              { text: input.trim(), override: picker },
              { onSuccess: () => setInput("") },
            );
          }}
        >
          <input
            data-testid="compose-input"
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

      {tid && <FileAttach threadId={tid} />}

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



function FileAttach({ threadId }: { threadId: number }) {
  const { data: files = [] } = useFiles();
  const attach = useAttachFileToThread(threadId);
  return (
    <details className="mt-6 ledger-surface px-5 py-3">
      <summary className="cursor-pointer ledger-eyebrow">Attach a file</summary>
      <div className="mt-2">
        <FileAttachPanel
          threadId={threadId}
          files={files}
          onAttach={(fileId) =>
            attach.mutate({ fileId, prompt: "Please review this document." })
          }
        />
      </div>
    </details>
  );
}
