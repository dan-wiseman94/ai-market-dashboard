import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Thread } from "@/api/threads";
import type { ThesisDirection } from "@/api/thesis";
import type { JournalDecision } from "@/api/journal";
import { useCreateThesis } from "@/hooks/useTheses";
import { useJournal, useCreateJournalEntry } from "@/hooks/useJournal";
import { useToast } from "@/hooks/useToast";

/**
 * State and submit handlers for the "new thesis from this thread" form and the
 * "close & journal" panel. The two are coupled by promote mode: promoting from
 * the journal panel opens the thesis form, and on success also logs a linked
 * journal entry.
 */
export function useThesisJournal(threadId: number | null, thread: Thread | undefined) {
  const navigate = useNavigate();
  const { push } = useToast();
  const createThesis = useCreateThesis();
  const createJournalEntry = useCreateJournalEntry();
  const { data: journalEntries = [] } = useJournal(threadId);

  const [showThesisForm, setShowThesisForm] = useState(false);
  const [thesisTitle, setThesisTitle] = useState("");
  const [thesisTicker, setThesisTicker] = useState("");
  const [thesisDirection, setThesisDirection] = useState<ThesisDirection>("bullish");
  const [thesisConviction, setThesisConviction] = useState(3);
  const [thesisRationale, setThesisRationale] = useState("");
  const [thesisTarget, setThesisTarget] = useState("");
  const [thesisInvalidation, setThesisInvalidation] = useState("");
  const [thesisInvalidationNote, setThesisInvalidationNote] = useState("");

  const [showJournalPanel, setShowJournalPanel] = useState(false);
  const [journalDecision, setJournalDecision] = useState<JournalDecision>("acted");
  const [journalNote, setJournalNote] = useState("");
  // promoteMode: when true, submitting the thesis form also logs a linked journal entry
  const [promoteMode, setPromoteMode] = useState(false);

  function resetThesisForm() {
    setThesisTitle("");
    setThesisTicker("");
    setThesisDirection("bullish");
    setThesisConviction(3);
    setThesisRationale("");
    setThesisTarget("");
    setThesisInvalidation("");
    setThesisInvalidationNote("");
  }

  function handleCreateThesis(e: React.FormEvent) {
    e.preventDefault();
    createThesis.mutate(
      {
        title: thesisTitle,
        ticker: thesisTicker,
        direction: thesisDirection,
        conviction: thesisConviction,
        rationale: thesisRationale,
        target_price: thesisTarget || null,
        invalidation_price: thesisInvalidation || null,
        invalidation_note: thesisInvalidationNote,
        thread_id: threadId,
        snapshot_id: thread?.pinned_snapshot_id ?? undefined,
        profile_id: thread?.profile?.id ?? undefined,
      },
      {
        onSuccess: (thesis) => {
          push({ kind: "success", text: `Thesis created: ${thesis.title}` });
          if (promoteMode && threadId) {
            createJournalEntry.mutate(
              {
                thread_id: threadId,
                decision: journalDecision,
                note: journalNote.trim() || "Promoted to thesis",
                thesis_id: thesis.id,
                snapshot_id: thread?.pinned_snapshot_id ?? undefined,
              },
              {
                onError: () =>
                  push({
                    kind: "error",
                    text: "Thesis created, but journaling the decision failed.",
                  }),
              },
            );
          }
          setShowThesisForm(false);
          setPromoteMode(false);
          resetThesisForm();
          navigate(`/theses/${thesis.id}`);
        },
        onError: (err) => push({ kind: "error", text: (err as Error).message }),
      },
    );
  }

  function handleLogDecision() {
    if (!threadId) return;
    createJournalEntry.mutate(
      {
        thread_id: threadId,
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
        onError: (err) => push({ kind: "error", text: (err as Error).message }),
      },
    );
  }

  return {
    showThesisForm,
    setShowThesisForm,
    thesisTitle,
    setThesisTitle,
    thesisTicker,
    setThesisTicker,
    thesisDirection,
    setThesisDirection,
    thesisConviction,
    setThesisConviction,
    thesisTarget,
    setThesisTarget,
    thesisInvalidation,
    setThesisInvalidation,
    thesisRationale,
    setThesisRationale,
    thesisInvalidationNote,
    setThesisInvalidationNote,
    handleCreateThesis,
    thesisPending: createThesis.isPending,
    showJournalPanel,
    setShowJournalPanel,
    journalDecision,
    setJournalDecision,
    journalNote,
    setJournalNote,
    handleLogDecision,
    journalPending: createJournalEntry.isPending,
    journalEntries,
    promoteMode,
    setPromoteMode,
  };
}
