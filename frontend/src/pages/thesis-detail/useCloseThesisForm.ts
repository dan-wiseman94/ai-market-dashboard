import { useState } from "react";
import { useCloseThesis } from "@/hooks/useTheses";
import { useToast } from "@/hooks/useToast";
import type { ThesisStatus } from "@/api/thesis";

type CloseStatus = Exclude<ThesisStatus, "open">;

export function useCloseThesisForm(thesisId: number) {
  const closeThesis = useCloseThesis();
  const { push } = useToast();

  const [showForm, setShowForm] = useState(false);
  const [status, setStatus] = useState<CloseStatus>("closed_win");
  const [note, setNote] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    closeThesis.mutate(
      { id: thesisId, body: { status, close_note: note } },
      {
        onSuccess: () => {
          push({ kind: "success", text: "Thesis closed." });
          setShowForm(false);
          setNote("");
        },
        onError: (err) =>
          push({ kind: "error", text: (err as Error).message }),
      },
    );
  };

  return {
    showForm,
    setShowForm,
    status,
    setStatus,
    note,
    setNote,
    handleSubmit,
    isPending: closeThesis.isPending,
  };
}
