import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { ThesisDirection } from "@/api/thesis";
import { useCreateThesis } from "@/hooks/useTheses";
import ThesisForm from "./thread-detail/ThesisForm";

const DIRECTIONS: ThesisDirection[] = ["bullish", "bearish", "neutral"];

function readDirection(raw: string | null): ThesisDirection {
  return DIRECTIONS.includes(raw as ThesisDirection) ? (raw as ThesisDirection) : "neutral";
}

/**
 * Standalone "new thesis" page reachable as a deep link — e.g. the Desk's
 * "Open thesis" action prefills ticker/direction/rationale from a finding.
 * The invalidation is intentionally left for the user (C4 pre-trade discipline).
 */
export default function NewThesisPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const create = useCreateThesis();

  const initialTicker = (params.get("ticker") ?? "").toUpperCase();
  const initialDirection = readDirection(params.get("direction"));

  const [title, setTitle] = useState(
    params.get("title") ?? (initialTicker ? `${initialTicker} ${initialDirection}` : ""),
  );
  const [ticker, setTicker] = useState(initialTicker);
  const [direction, setDirection] = useState<ThesisDirection>(initialDirection);
  const [conviction, setConviction] = useState(3);
  const [rationale, setRationale] = useState(params.get("rationale") ?? "");
  const [target, setTarget] = useState("");
  const [invalidation, setInvalidation] = useState("");
  const [invalidationNote, setInvalidationNote] = useState("");
  const [error, setError] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const thesis = await create.mutateAsync({
        title,
        ticker,
        direction,
        rationale,
        conviction,
        target_price: target || null,
        invalidation_price: invalidation || null,
        invalidation_note: invalidationNote || undefined,
      });
      navigate(`/theses/${thesis.id}`);
    } catch {
      setError("Could not save — a rationale and an invalidation (price or note) are required.");
    }
  };

  return (
    <div className="px-8 py-8 max-w-3xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold mb-4">New thesis</h1>
      {error && (
        <p className="mb-3 text-[13px] text-loss-400" role="alert">
          {error}
        </p>
      )}
      <ThesisForm
        promoteMode={false}
        title={title}
        onTitleChange={setTitle}
        ticker={ticker}
        onTickerChange={setTicker}
        direction={direction}
        onDirectionChange={setDirection}
        conviction={conviction}
        onConvictionChange={setConviction}
        rationale={rationale}
        onRationaleChange={setRationale}
        target={target}
        onTargetChange={setTarget}
        invalidation={invalidation}
        onInvalidationChange={setInvalidation}
        invalidationNote={invalidationNote}
        onInvalidationNoteChange={setInvalidationNote}
        pending={create.isPending}
        onSubmit={onSubmit}
        onCancel={() => navigate(-1)}
      />
    </div>
  );
}
