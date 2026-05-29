import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useSnapshot } from "@/hooks/useSnapshot";
import {
  useCompareMessage,
  useRenameThread,
  useSendMessage,
  useStopMessage,
  useThread,
} from "@/hooks/useThread";
import ThreadExportButton from "@/components/ThreadExportButton";
import CompareDialog from "@/components/CompareDialog";
import Conversation from "./thread-detail/Conversation";
import Composer from "./thread-detail/Composer";
import EditableTitle from "./thread-detail/EditableTitle";
import FileAttach from "./thread-detail/FileAttach";
import ThesisForm from "./thread-detail/ThesisForm";
import JournalPanel from "./thread-detail/JournalPanel";
import { useLiveMessages } from "./thread-detail/useLiveMessages";
import { useThesisJournal } from "./thread-detail/useThesisJournal";
import { RelatedObservations } from "@/components/RelatedObservations";

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const tid = id ? parseInt(id, 10) : null;
  const snapshotId = search.get("snapshot") ? parseInt(search.get("snapshot")!, 10) : null;

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  const thesisJournal = useThesisJournal(tid, thread);
  const { ordered, branchesByParent, toolCalls } = useLiveMessages(tid, thread, refetch);

  const [activeBranchByParent, setActiveBranchByParent] = useState<Record<number, number>>({});
  const [picker, setPicker] = useState({ provider: "claude", model: "claude-sonnet-4-6" });
  const [showCompare, setShowCompare] = useState(false);
  const [input, setInput] = useState("");

  const send = useSendMessage(tid ?? 0);
  const compare = useCompareMessage(tid ?? 0);
  const stop = useStopMessage(tid ?? 0);
  const rename = useRenameThread(tid ?? 0);

  if (!thread) {
    return (
      <main className="px-8 py-8 max-w-4xl mx-auto">
        <div className="font-mono text-[13px] text-ink-400">Loading thread…</div>
      </main>
    );
  }

  const handleSend = () => {
    if (!input.trim()) return;
    send.mutate(
      { text: input.trim(), override: picker },
      { onSuccess: () => setInput("") },
    );
  };

  return (
    <main className="px-8 py-8 max-w-4xl mx-auto ledger-fade-in">
      {/* Masthead */}
      <header className="mb-8 pb-6 border-b border-rule">
        <div className="flex items-center gap-3 mb-3">
          <span className="ledger-eyebrow">Thread · #{thread.id}</span>
          <span className="flex-1 h-px bg-rule-soft" />
          <ThreadExportButton threadId={tid!} />
          <button
            onClick={() => thesisJournal.setShowJournalPanel((v) => !v)}
            className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
            data-testid="journal-panel-btn"
          >
            ✎ Close & journal
          </button>
          <button
            onClick={() => thesisJournal.setShowThesisForm((v) => !v)}
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
        <EditableTitle
          title={thread.title}
          onSave={(t) => rename.mutate(t)}
          pending={rename.isPending}
        />
      </header>

      {/* New thesis inline form */}
      {thesisJournal.showThesisForm && (
        <ThesisForm
          promoteMode={thesisJournal.promoteMode}
          title={thesisJournal.thesisTitle}
          onTitleChange={thesisJournal.setThesisTitle}
          ticker={thesisJournal.thesisTicker}
          onTickerChange={thesisJournal.setThesisTicker}
          direction={thesisJournal.thesisDirection}
          onDirectionChange={thesisJournal.setThesisDirection}
          conviction={thesisJournal.thesisConviction}
          onConvictionChange={thesisJournal.setThesisConviction}
          target={thesisJournal.thesisTarget}
          onTargetChange={thesisJournal.setThesisTarget}
          invalidation={thesisJournal.thesisInvalidation}
          onInvalidationChange={thesisJournal.setThesisInvalidation}
          pending={thesisJournal.thesisPending}
          onSubmit={thesisJournal.handleCreateThesis}
          onCancel={() => {
            thesisJournal.setShowThesisForm(false);
            thesisJournal.setPromoteMode(false);
          }}
        />
      )}

      {/* Close & journal panel */}
      {thesisJournal.showJournalPanel && (
        <JournalPanel
          decision={thesisJournal.journalDecision}
          onDecisionChange={thesisJournal.setJournalDecision}
          note={thesisJournal.journalNote}
          onNoteChange={thesisJournal.setJournalNote}
          pending={thesisJournal.journalPending}
          onLogDecision={thesisJournal.handleLogDecision}
          onPromote={() => {
            thesisJournal.setPromoteMode(true);
            thesisJournal.setShowThesisForm(true);
          }}
          onClose={() => thesisJournal.setShowJournalPanel(false)}
          entries={thesisJournal.journalEntries}
        />
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
      <Conversation
        ordered={ordered}
        branchesByParent={branchesByParent}
        toolCalls={toolCalls}
        activeBranchByParent={activeBranchByParent}
        onSelectBranch={(parentId, cid) => setActiveBranchByParent((s) => ({ ...s, [parentId]: cid }))}
        onStop={(messageId) => stop.mutate(messageId)}
        threadChannel={tid ? `thread.${tid}` : null}
      />

      {/* Compose bar */}
      <Composer
        picker={picker}
        onPickerChange={setPicker}
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        onCompare={() => setShowCompare(true)}
      />

      {tid && <FileAttach threadId={tid} />}

      {/* Related observations — keyed off the thread's pinned snapshot message, if present */}
      {tid && <RelatedObservations kind="message" id={tid} />}

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
