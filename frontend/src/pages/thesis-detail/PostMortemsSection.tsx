import { useRunPostmortem } from "@/hooks/useTheses";
import { useToast } from "@/hooks/useToast";
import { EmptyState } from "@/components/EmptyState";
import { PostMortemCard } from "./PostMortemCard";
import type { PostMortem } from "@/api/thesis";

export function PostMortemsSection({
  thesisId,
  postmortems,
}: {
  thesisId: number;
  postmortems: PostMortem[];
}) {
  const runPostmortem = useRunPostmortem();
  const { push } = useToast();

  const sorted = [...postmortems].sort(
    (a, b) => a.horizon_days - b.horizon_days,
  );

  return (
    <section>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="ledger-eyebrow">Post-mortems</h2>
        <span className="flex-1 h-px bg-rule" />
        <button
          type="button"
          className="ledger-ghost px-3 py-1 text-[12px]"
          onClick={() =>
            runPostmortem.mutate(thesisId, {
              onSuccess: () => push({ kind: "success", text: "Post-mortem queued." }),
              onError: (err) =>
                push({ kind: "error", text: (err as Error).message }),
            })
          }
          disabled={runPostmortem.isPending}
          data-testid="run-postmortem-btn"
        >
          {runPostmortem.isPending ? "Queuing…" : "Run now"}
        </button>
      </div>
      {sorted.length === 0 ? (
        <EmptyState
          title="No post-mortems yet"
          body="Post-mortems are created automatically when a thesis is saved."
        />
      ) : (
        <div className="space-y-4">
          {sorted.map((pm) => (
            <PostMortemCard key={pm.id} pm={pm} />
          ))}
        </div>
      )}
    </section>
  );
}
