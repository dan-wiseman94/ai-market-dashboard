import { Link } from "react-router-dom";
import { useParams } from "react-router-dom";
import { useThesis, useUpdateThesis } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ThesisMasthead } from "./thesis-detail/ThesisMasthead";
import { ThesisFields } from "./thesis-detail/ThesisFields";
import { SourceLinks } from "./thesis-detail/SourceLinks";
import { CloseThesisForm } from "./thesis-detail/CloseThesisForm";
import { PostMortemsSection } from "./thesis-detail/PostMortemsSection";
import Toggle from "@/components/ui/Toggle";
import type { Thesis } from "@/api/thesis";
import { TrackRecordHint } from "@/components/TrackRecordHint";

function PriceGuardToggle({ thesis }: { thesis: Thesis }) {
  const hasTargetOrInvalidation =
    thesis.target_price != null || thesis.invalidation_price != null;
  const hasProfile = thesis.profile_id != null;
  const canEnable = hasTargetOrInvalidation && hasProfile;
  const update = useUpdateThesis();

  const disabledReason = !hasTargetOrInvalidation
    ? "Set a target or invalidation price to enable"
    : !hasProfile
      ? "Attach a profile to enable"
      : undefined;

  return (
    <section className="mb-8 pb-6 border-b border-rule">
      <h2 className="ledger-eyebrow mb-3">Price guard</h2>
      <div className="flex items-center gap-3">
        <Toggle
          id="guard-toggle"
          label="Price guard"
          checked={thesis.guard_enabled}
          onChange={(next) => update.mutate({ id: thesis.id, body: { guard_enabled: next } })}
          disabled={!canEnable || update.isPending}
        />
        <label
          htmlFor="guard-toggle"
          className="text-sm text-ink-300 cursor-pointer"
        >
          Auto-trigger on target / invalidation cross
        </label>
        {disabledReason && (
          <span className="text-xs text-ink-500 italic" title={disabledReason}>
            ({disabledReason})
          </span>
        )}
      </div>
      {thesis.guard_trigger_id != null && (
        <p className="mt-2 text-xs text-ink-400">
          Linked trigger:{" "}
          <Link
            to={`/triggers/${thesis.guard_trigger_id}`}
            className="text-copper-400 hover:text-copper-300"
            data-testid="guard-trigger-link"
          >
            #{thesis.guard_trigger_id}
          </Link>
        </p>
      )}
    </section>
  );
}

export default function ThesisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tid = id ? parseInt(id, 10) : null;
  const { data: thesis, isLoading } = useThesis(tid);

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!thesis) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <EmptyState title="Thesis not found" body="This thesis does not exist or has been deleted." />
      </div>
    );
  }

  return (
    <main className="max-w-3xl mx-auto p-6 ledger-fade-in">
      <ThesisMasthead thesis={thesis} />
      <TrackRecordHint
        ticker={thesis.ticker}
        direction={thesis.direction}
        conviction={thesis.conviction}
      />
      <ThesisFields thesis={thesis} />
      <SourceLinks thesis={thesis} />
      <PriceGuardToggle thesis={thesis} />
      {thesis.status === "open" && <CloseThesisForm thesisId={thesis.id} />}
      <PostMortemsSection thesisId={thesis.id} postmortems={thesis.postmortems} />
    </main>
  );
}
