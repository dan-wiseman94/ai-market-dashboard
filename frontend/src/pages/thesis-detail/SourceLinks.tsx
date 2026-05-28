import { Link } from "react-router-dom";
import type { Thesis } from "@/api/thesis";

export function SourceLinks({ thesis }: { thesis: Thesis }) {
  if (!thesis.thread_id && !thesis.snapshot_id) return null;

  return (
    <section className="mb-8 ledger-surface px-5 py-4">
      <div className="ledger-eyebrow mb-3">Source</div>
      <div className="flex gap-4">
        {thesis.thread_id && (
          <Link
            to={`/threads/${thesis.thread_id}`}
            className="font-mono text-[12px] text-copper-400 hover:text-copper-300 transition-colors"
          >
            Thread #{thesis.thread_id} →
          </Link>
        )}
        {thesis.snapshot_id && (
          <span className="font-mono text-[12px] text-ink-400">
            Snapshot #{thesis.snapshot_id}
          </span>
        )}
        {thesis.review_thread_id && (
          <Link
            to={`/threads/${thesis.review_thread_id}`}
            className="font-mono text-[12px] text-ink-400 hover:text-copper-300 transition-colors"
          >
            Review thread #{thesis.review_thread_id} →
          </Link>
        )}
      </div>
    </section>
  );
}
