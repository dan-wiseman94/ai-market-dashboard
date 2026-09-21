import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";

/**
 * The AI paragraph over the book, or an honest account of why there isn't one.
 *
 * `book_narrative()` returns "" both when the feature is off
 * (`book_narrative_enabled`) and when no provider / cap allows the call — the
 * numbers are computed either way, so say that rather than showing a blank panel.
 */
export default function BookNarrativePanel({ narrative }: { narrative: string }) {
  if (narrative) return <p className="mt-2 text-ink/80">{narrative}</p>;
  return (
    <EmptyState
      title="No written narrative for this reading"
      body={
        "Every number on this page is computed without the AI. The paragraph is written only " +
        "when the book narrative feature is on and an AI provider is configured and under its cost cap."
      }
      action={
        <Link
          to="/settings"
          className="rounded border border-rule px-3 py-1 text-sm text-ink-300 hover:text-copper-300"
        >
          Settings → Features
        </Link>
      }
    />
  );
}
